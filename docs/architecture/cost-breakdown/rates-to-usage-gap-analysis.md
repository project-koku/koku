# RatesToUsage — Gap Analysis

Integrity and correctness gaps in the `rates_to_usage` table and its FK relationships.

| Gap | Severity | Summary |
|-----|----------|---------|
| [GAP-1](#gap-1-sync_rate_table-deletes-rate-rows-still-referenced-by-rates_to_usagerate_id) | Bug / HTTP 500 | `sync_rate_table()` deletes `Rate` rows while RTU holds live FKs |
| [GAP-2](#gap-2-cost-model-deletion-doesnt-null-rates_to_usagecost_model_id-reliably) | Data integrity | Cost model deletion leaves stale `cost_model_id` on RTU rows |
| [GAP-3](#gap-3-price-list-deletion-cascades-to-rate-deletion--same-fk-hazard-as-gap-1) | Bug / HTTP 500 | Price list deletion triggers same FK hazard as GAP-1 |
| [GAP-4](#gap-4-report_period_id-is-a-bare-integerfield--no-fk-no-automatic-cascade-on-deletion) | Orphan rows | `report_period_id` is a bare `IntegerField` — orphans left by single-period deletes and provider-UUID purge |
| [GAP-5](#gap-5-missing-indexes-on-rate_id-and-cost_model_id-for-fk-set_null-lookups) | Performance | No index on `rate_id` or `cost_model_id` — SET_NULL queries scan all partitions |
| [GAP-6](#gap-6-monthly-cost-sql-inserts-rtu-rows-without-a-preceding-delete) | Bug / duplicate costs | Monthly cost SQL INSERTs into RTU without a DELETE — stale rows accumulate across runs |
| [GAP-7](#gap-7-tag-usage-cost-sql-inserts-rtu-rows-without-a-preceding-delete) | Bug / duplicate costs | Tag usage cost SQL INSERTs into RTU without a DELETE — same accumulation pattern |

---

## Design context

`rates_to_usage` is a **partitioned tenant-schema table** with:

- `rate = ForeignKey("cost_models.Rate", on_delete=SET_NULL, null=True)`
- `cost_model = ForeignKey("cost_models.CostModel", on_delete=SET_NULL, null=True)`
- `report_period_id = IntegerField(null=True)` — intentionally bare, no FK

Because `rates_to_usage` lives in tenant schemas (`org1234567`, etc.) and the FK targets (`Rate`, `CostModel`) also live in tenant schemas, Django's ORM FK collector must be inside the correct `schema_context` to find and null referencing rows before a delete. Without that guard, the DB-level FK constraint fires an `IntegrityError`.

---

## GAP-1: `sync_rate_table()` deletes `Rate` rows still referenced by `rates_to_usage.rate_id`

**Severity:** Bug — HTTP 500 (`IntegrityError`)

**Trigger:** Any cost model or price list edit that removes a rate (diff sync drops stale `Rate` rows).

**Root cause:** [`rate_sync.py` line 197](../../koku/cost_models/rate_sync.py) calls
`Rate.objects.filter(...).delete()` with no active `schema_context`. Django's `SET_NULL`
collector issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` — but
with no schema context it queries the wrong schema, finds no rows to null, and the
DB-level FK constraint fires.

**Current state:** No pre-delete nullification. `sync_rate_table()` deletes `Rate` rows unconditionally.

**Fix:** Before the delete, within `schema_context(schema)`:

```python
RatesToUsage.objects.filter(rate_id__in=to_delete_uuids).update(rate=None)
Rate.objects.filter(price_list=price_list, uuid__in=to_delete_uuids).delete()
```

`sync_rate_table()` needs a `schema` kwarg (or nullable parameter — skip the update when absent for callers that have no tenant context).

**Design note:** Chosen over CASCADE-delete because each RTU row carries real cost values
(`calculated_cost`, `custom_name`) that `aggregate_rates_to_daily_summary.sql` reads by
`custom_name`, not `rate_id`. Nulling keeps historical cost data intact.

---

## GAP-2: Cost model deletion leaves stale RTU rows until next worker cycle

**Severity:** Data integrity risk (timing window)

**Trigger:** User deletes a `CostModel` via the API.

**Root cause:** `cost_model = ForeignKey(CostModel, on_delete=SET_NULL)`. After deletion,
RTU rows retain `cost_model_id = NULL` but still hold `calculated_cost` values. The daily
summary cleanup (`_cleanup_stale_rtu_costs`) only runs during the **next**
`update_cost_model_costs` cycle, leaving a window where stale cost data remains.

**Current state:** RTU rows survive cost model deletion with nulled `cost_model_id` until
the next worker run zeroes out the daily summary.

**Fix:** Change to `on_delete=CASCADE` for the `cost_model` FK.

Cost model deletion is a permanent, intentional action — RTU rows for a deleted cost model
have no further use. CASCADE cleans them up immediately and eliminates the orphan window
entirely. The daily summary cleanup (`_cleanup_stale_rtu_costs`) still needs to run to zero
out cost columns in `reporting_ocpusagelineitem_daily_summary`, which CASCADE on RTU does
not touch.

**Why CASCADE is safe here but not for `rate_id`:** `Rate` rows are deleted during normal
cost model edits (every time a rate's metric or type changes, `sync_rate_table` replaces
the `Rate` row). CASCADE on `rate_id` would delete all RTU rows on every routine save.
`CostModel` deletion is a one-time permanent action — CASCADE semantics are appropriate.

---

## GAP-3: Price list deletion cascades to `Rate` deletion — same FK hazard as GAP-1

**Severity:** Bug — HTTP 500 (`IntegrityError`)

**Trigger:** User deletes a `PriceList`. `PriceList` deletion cascades to `Rate` rows via
`Rate.price_list` (CASCADE). `Rate` deletion then hits the same `rates_to_usage.rate_id`
FK as GAP-1.

**Root cause:** `PriceList` delete → `Rate` CASCADE fires **at the DB level**. Django's
SET_NULL collector for `RatesToUsage.rate_id` cannot intercept a DB-level cascade. Same
schema-context gap as GAP-1.

**Current state:** `PriceListManager` has no pre-delete RTU nullification.

**Fix:** In `PriceListManager.delete()`, within `schema_context(schema)`, null RTU rows
before deleting the price list:

```python
RatesToUsage.objects.filter(rate__price_list=price_list).update(rate=None)
```

The same `schema` kwarg change required for GAP-1 suffices here.

---

## GAP-4: `report_period_id` is a bare `IntegerField` — no FK, no automatic cascade on deletion

**Severity:** Orphan rows

**Trigger:** An `OCPUsageReportPeriod` row is deleted (targeted re-ingestion, provider purge, data cleanup, or cascade from provider deletion).

**Root cause:** `RatesToUsage.report_period_id = IntegerField(null=True)` — intentionally
not a `ForeignKey` to `OCPUsageReportPeriod`. Django and PostgreSQL have no record of the
relationship, so deleting a report period leaves orphaned RTU rows with a stale integer ID.

**Current state:** Cleanup is manually special-cased:
- [`ocp_report_db_cleaner.py`](../../koku/masu/processor/ocp/ocp_report_db_cleaner.py)
  lists `"rates_to_usage"` in its partition table list → swept during **date-based** partition cleanup.
- `_cleanup_stale_rtu_costs()` deletes by `report_period_id` during cost update cycles.

There are two call sites where neither path fires and RTU rows are orphaned:

1. **Targeted single-period deletes** (e.g. during re-ingestion) — these delete a specific `OCPUsageReportPeriod` without dropping a partition or running a cost update cycle.

2. **Provider-UUID purge path** — `purge_expired_report_data(provider_uuid=...)` cascade-deletes `OCPUsageReportPeriod` and its FK-linked tables, but the bare `IntegerField` means the cascade does not reach RTU. No partition is dropped for this path.

**Fix (option A — preferred):** Add an explicit delete at each call site:

```python
# Single-period re-ingestion
with schema_context(schema):
    RatesToUsage.objects.filter(
        report_period_id=period.id,
        source_uuid=provider_uuid,
    ).delete()

# Provider-UUID purge (covers all periods for the provider)
with schema_context(schema):
    RatesToUsage.objects.filter(source_uuid=provider_uuid).delete()
```

**Fix (option B):** Convert to a real `ForeignKey(OCPUsageReportPeriod, on_delete=CASCADE, null=True, db_constraint=False)` — Django enforces the relationship in Python without a DB constraint (safe for partitioned tables).

---

## GAP-5: Missing indexes on `rate_id` and `cost_model_id` for FK SET_NULL lookups

**Severity:** Performance

**Trigger:** Any `Rate` or `CostModel` deletion that triggers a SET_NULL update (GAP-1,
GAP-2, GAP-3 fix paths, or Django's collector).

**Root cause:** Current indexes on `rates_to_usage`:

| Index name | Columns |
|---|---|
| `ratestousage_start_src_rp_idx` | `(usage_start, source_uuid, report_period_id)` |
| `ratestousage_namespace_idx` | `(namespace)` |
| `ratestousage_cluster_idx` | `(cluster_id)` |
| `ratestousage_custom_name_idx` | `(custom_name)` |
| `ratestousage_monthly_cost_idx` | `(monthly_cost_type)` |
| `ratestousage_label_hash_idx` | `(label_hash)` |

There is **no index on `rate_id` or `cost_model_id`**. A SET_NULL `UPDATE` of the form
`WHERE rate_id IN (...)` requires a sequential scan of every partition in the tenant schema.

**Fix:** Add a new migration (e.g. `0350_ratestousage_fk_indexes.py`):

```python
migrations.AddIndex(
    model_name="ratestousage",
    index=models.Index(fields=["rate_id"], name="ratestousage_rate_id_idx"),
),
migrations.AddIndex(
    model_name="ratestousage",
    index=models.Index(fields=["cost_model_id"], name="ratestousage_cost_model_id_idx"),
),
```

---

## GAP-6: Monthly cost SQL inserts RTU rows without a preceding DELETE

**Severity:** Bug — duplicate / stale costs

**Trigger:** Any pipeline run after a monthly rate (node, cluster, PVC, VM) was removed or changed.

**Root cause:** [`monthly_cost_cluster_and_node.sql`](../../koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql), `monthly_cost_persistentvolumeclaim.sql`, and `monthly_cost_virtual_machine.sql` are pure INSERTs — no preceding DELETE from `rates_to_usage`. The per-month cleanup in `_delete_monthly_cost_model_data` (called by `_update_monthly_cost`) targets **daily summary only** via [`delete_monthly_cost.sql`](../../koku/masu/database/sql/openshift/cost_model/delete_monthly_cost.sql). The `insert_usage_rates_to_usage.sql` step-1 DELETE is scoped to `monthly_cost_type IS NULL`, so monthly RTU rows (`monthly_cost_type = 'Node'`, `'Cluster'`, `'PVC'`, `'VM'`) survive.

On the next pipeline run, fresh monthly rows are inserted alongside the stale ones. Both are read by `aggregate_rates_to_daily_summary.sql`, doubling (or otherwise corrupting) the monthly cost component in daily summary.

**Note:** The tag-monthly variants (`node_cost_by_tag.sql`, `monthly_cost_persistentvolumeclaim_by_tag.sql`) **do** include a scoped DELETE. Only the non-tag monthly files lack it.

**Fix:** Prepend a scoped DELETE to each monthly cost SQL file:

```sql
DELETE FROM {{schema | sqlsafe}}.rates_to_usage
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}}
  AND monthly_cost_type = {{rate_type}};  -- 'Node', 'Cluster', 'PVC', or 'VM'
```

Alternatively, add a single pre-step in `_update_monthly_cost` that deletes all `monthly_cost_type IN ('Node','Cluster','PVC','VM','Node_Core_Month',...)` RTU rows before dispatching any monthly SQL.

---

## GAP-7: Tag usage cost SQL inserts RTU rows without a preceding DELETE

**Severity:** Bug — duplicate / stale costs

**Trigger:** Any pipeline run after a tag-based usage rate was removed, renamed, or retagged.

**Root cause:** [`infrastructure_tag_rates.sql`](../../koku/masu/database/sql/openshift/cost_model/infrastructure_tag_rates.sql), `supplementary_tag_rates.sql`, `default_infrastructure_tag_rates.sql`, and `default_supplementary_tag_rates.sql` are pure INSERTs. `_delete_tag_usage_costs` deletes daily summary rows with `monthly_cost_type IN ('Tag', 'Node_Core_Hour')` but **never touches `rates_to_usage`**. Prior-run tag RTU rows with the removed or renamed `custom_name` / `rate_id` survive and are re-read by `aggregate_rates_to_daily_summary`.

**Fix:** `_delete_tag_usage_costs` (or the SQL files themselves) must also DELETE from `rates_to_usage`:

```python
# In _delete_tag_usage_costs, inside schema_context:
with schema_context(self._schema):
    RatesToUsage.objects.filter(
        usage_start__gte=start_date,
        usage_start__lte=end_date,
        source_uuid=source_uuid,
        report_period_id=report_period_id,
        monthly_cost_type__in=["Tag", "Node_Core_Hour"],
    ).delete()
```


---

## Files affected

| Gap | File | Change |
|-----|------|--------|
| GAP-1 | `koku/cost_models/rate_sync.py` | Pre-delete RTU `rate_id` nullification + `schema` kwarg |
| GAP-2 | `koku/reporting/migrations/035X_rtu_costmodel_cascade.py` + `koku/reporting/provider/ocp/models.py` | Change `cost_model` FK to `on_delete=CASCADE` |
| GAP-3 | `koku/cost_models/price_list_manager.py` | Pre-delete RTU `rate_id` nullification |
| GAP-4 | `koku/masu/processor/ocp/ocp_report_db_cleaner.py` (or relevant accessor) | Explicit `RatesToUsage` delete at single-period re-ingestion **and** provider-UUID purge call sites |
| GAP-5 | `koku/reporting/migrations/0350_ratestousage_fk_indexes.py` | `AddIndex`: `rate_id`, `cost_model_id` |
| GAP-6 | `koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql`, `monthly_cost_persistentvolumeclaim.sql`, `monthly_cost_virtual_machine.sql` (+ self_hosted_sql equivalents) | Add scoped DELETE before INSERT |
| GAP-7 | `koku/masu/processor/ocp/ocp_cost_model_cost_updater.py` (`_delete_tag_usage_costs`) | Also delete RTU rows with `monthly_cost_type IN ('Tag','Node_Core_Hour')` |
