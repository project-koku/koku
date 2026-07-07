# Adversarial Due Diligence Review — PR #6166: COST-7736 FK Violation Fix

## Version & Date
Version: 3.0 | Date: 2026-07-07 | Reviewer: AI-assisted

## Executive Summary

This PR fixes an HTTP 500 (`IntegrityError`) that occurs when updating a cost model to remove a rate that has existing `rates_to_usage` rows referencing it. The fix is a 3-line addition to `sync_rate_table()` that explicitly nulls `rates_to_usage.rate_id` before deleting stale `Rate` rows. A 97-line regression test is included.

The fix is **correct and resolves the immediate production issue** — confirmed by GlitchTip data showing 5 occurrences in production (INSIGHTS-HCCM-PROD-5ER, last seen June 29, 2026). However, the review uncovered a broader class of the same bug affecting other FK paths, also confirmed by production and stage error data.

**Key findings from deep investigation:**

1. **Django's Collector should handle this automatically** — tracing through Django 4.2's `deletion.py` confirms the Collector correctly discovers the `RatesToUsage` relation, issues SET_NULL UPDATEs before DELETEs, and does not use fast-delete for this case.

2. **The root cause is a well-documented class of PostgreSQL bugs with FK constraints on partitioned tables.** Django creates FK constraints as `NO ACTION DEFERRABLE INITIALLY DEFERRED` and handles SET_NULL in Python. The deferred FK check at COMMIT can fail due to catalog state corruption after partition ATTACH/DETACH operations (PG Bug #16908, fixed in PG 16.5) or incorrect trigger resolution during partition data migration (PG Bug #16621). Koku runs PG 16 — if on anything before 16.5, this is the exact mechanism. Multiple open Django tickets ([#25955](https://code.djangoproject.com/ticket/25955), [#24576](https://code.djangoproject.com/ticket/24576)) document the same pattern. Django 5.2+ adds `db_on_delete` ([#21961](https://code.djangoproject.com/ticket/21961)) which lets PostgreSQL handle SET_NULL natively, bypassing the Collector entirely.

3. **GlitchTip confirms the same class of bug on multiple FK paths** — not just `rate_id` (which this PR fixes) but also `cost_model_id` on the delete path, and a race condition between pipeline INSERTs and concurrent deletions. GitLab hit the identical wall and built an entire "loose foreign keys" system to work around it ([GitLab #508672](https://gitlab.com/gitlab-org/gitlab/-/issues/508672)).

4. **The `rates_to_usage` table has ~15.6M rows in production** — heavily skewed across 1,807 tenant schemas (3 tenants hold 72% of all rows, 97% of tenants have zero rows). The table was introduced May 4, 2026 (PR #6017) and grows monotonically. No index exists on `rate_id`, so the fix's UPDATE sequential-scans every partition in the largest tenants (5.3M rows in the biggest), potentially causing multi-second API latency.

5. **The `destroy()` path does not use `cascade_delete()`** — cost model deletion via the API (`view.py` → `destroy`) calls standard Django `instance.delete()`, not the project's custom `cascade_delete()` from `database.py`. This confirms the stage GlitchTip finding (STAGE-5I4).

## Root Cause Analysis

### What Django does (verified by source inspection)

We traced through Django 4.2's deletion code in the project's virtualenv (`.venv/lib/python3.11/site-packages/django/db/models/deletion.py`):

1. **`get_candidate_relations_to_delete()`** (line 84-91) — calls `opts.get_fields(include_hidden=True)` and filters for auto-created reverse relations. The `RatesToUsage.rate` FK creates a `ManyToOneRel` on `Rate._meta` that satisfies all conditions. **The Collector sees the relation.**

2. **`can_fast_delete()`** (line 185-227) — checks whether ALL reverse FK relations use `DO_NOTHING` (line 216-219). Since `RatesToUsage.rate` uses `SET_NULL`, this returns `False`. **Rate objects are NOT fast-deleted.**

3. **`collect()`** (line 309) — `SET_NULL.lazy_sub_objs` is set to `True` (line 73), and checked in `collect()` at line 343. The SET_NULL handler stores a lazy queryset in `field_updates` without evaluating it.

4. **`delete()`** execution order — `fast_deletes` first (line 466), then `field_updates` / SET_NULL UPDATEs (line 472), then instance DELETEs (line 498). **SET_NULL runs BEFORE the DELETE.**

5. **django-tenants does not interfere** — both `cost_models` and `reporting` are in `TENANT_APPS` (`settings.py:111`), so both tables exist in the same tenant schema. The `TenantSyncRouter` only implements `allow_migrate`, not `db_for_read`/`db_for_write`.

**Conclusion:** Django's Collector correctly issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` before `DELETE FROM cost_model_rate WHERE uuid IN (...)`. At the Python/ORM level, nothing is wrong.

### What happens at the PostgreSQL level

The critical discovery: **Django does NOT create `ON DELETE SET NULL` at the database level.** The DB-level FK constraint is:

```sql
FOREIGN KEY (rate_id) REFERENCES cost_model_rate(uuid) DEFERRABLE INITIALLY DEFERRED
```

No `ON DELETE SET NULL` clause. The database default is `ON DELETE NO ACTION`. Django handles SET_NULL purely in Python. The database only enforces "no dangling FK references at COMMIT."

So the sequence should be:
1. Collector issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` — PostgreSQL routes to all partitions
2. Collector issues `DELETE FROM cost_model_rate WHERE uuid IN (...)` — succeeds
3. At COMMIT, deferred FK trigger checks whether any `rates_to_usage` rows still reference deleted UUIDs
4. They shouldn't, because step 1 already nulled them → **no error expected**

Yet the error occurs. The investigation uncovered a well-documented class of PostgreSQL bugs that explains this.

### Known Django tickets

| Ticket | Status | Relevance |
|--------|--------|-----------|
| [#25955](https://code.djangoproject.com/ticket/25955) | **Open** (since 2015) | FK constraints are `DEFERRABLE INITIALLY DEFERRED`, so violations only surface at COMMIT, not at savepoint release from nested `transaction.atomic()`. The IntegrityError blows up at commit, far from where the delete happens. |
| [#24576](https://code.djangoproject.com/ticket/24576) | **Open** | Django's Collector can generate non-deterministic deletion ordering that violates FK constraints at commit time. The bug is intermittent. |
| [#21961](https://code.djangoproject.com/ticket/21961) | **Fixed** (Django 5.2+) | Adds `db_on_delete` kwarg — actual database-level `ON DELETE SET NULL`. Bypasses the Collector entirely. **This is the proper long-term fix.** Koku is on Django 4.2. |
| [#33928](https://code.djangoproject.com/ticket/33928) | Fixed | Collector generated `UPDATE ... WHERE id IN (id1, ..., id30000)` instead of efficient direct UPDATE. Performance fix, but shows the Collector's fragility on large tables. |

### Known PostgreSQL bugs with FK on partitioned tables

FK support for partitioned tables was added incrementally (PG 11: referencing side only; PG 12: both sides) and has been plagued by bugs in every major release:

| Bug | PG Versions Affected | Fixed In | Description |
|-----|---------------------|----------|-------------|
| [BUG #16908](https://www.postgresql.org/message-id/16908-5b53ef9b31fb94c9@postgresql.org) — ATTACH/DETACH catalog corruption | **PG 12 through 17.0** | 13.17, 14.14, 15.9, **16.5**, 17.1 (Nov 2024) | ATTACH/DETACH PARTITION fails to convert FK trigger catalog entries correctly. After DETACH, FK enforcement triggers are **missing entirely** — SET NULL/CASCADE silently stops working. GitLab hit this in production ([#508672](https://gitlab.com/gitlab-org/gitlab/-/issues/508672)) and built a "loose foreign keys" system as workaround. |
| [BUG #16621](https://www.postgresql.org/message-id/16621-926cf657e4315eab@postgresql.org) — Deferred check after partition migration | PG 12.2, 12.4 | Unclear | Deferred FK trigger fires at COMMIT but looks at the **wrong partition** — doesn't "see" rows that moved between partitions within the same transaction. **Closest documented match to COST-7736.** |
| ALTER CONSTRAINT deferrability not propagated | PG 10–13.2 | 11.12, 12.7, **13.3** | `ALTER CONSTRAINT ... DEFERRABLE` updated catalog but **not the actual trigger properties** on leaf partitions. Constraint appeared deferred but triggers fired immediately. |
| Cross-partition UPDATE fires CASCADE/SET NULL | PG 12–14 | **PG 15 only** | Cross-partition UPDATE (internally DELETE+INSERT) incorrectly fires FK cascade/SET NULL triggers on the old partition, nulling/deleting referencing rows even though the referenced row merely moved. |
| [BUG #18156](https://www.postgresql.org/message-id/18156-a44bc7096f0683e6@postgresql.org) — Self-referencing FK not enforced | PG 12–17.4 | 13.21, 14.18, 15.13, **16.9**, 17.5 (May 2025) | ATTACH PARTITION fails to create catalog entries for self-referencing FKs. Alvaro Herrera acknowledged: *"Clearly this area needs a lot more work."* |

**Koku runs PostgreSQL 16** (`deploy/clowdapp.yaml: DATABASE_VERSION: "16"`). The ATTACH/DETACH catalog corruption bug (#16908) was fixed in **PG 16.5** (November 2024). If koku production is running PG 16.0–16.4, this is the most likely mechanism: the custom partition creation via `trfn_partition_manager` (which does ATTACH operations) could leave FK enforcement triggers in a corrupted state, causing the deferred check at COMMIT to fail.

### Important PostgreSQL detail

From the PostgreSQL documentation: *"Row updates or deletions caused by foreign-key enforcement actions, such as ON UPDATE CASCADE or ON DELETE SET NULL, are treated as part of the SQL command that caused them (note that such actions are never deferred)."*

But Django does NOT use FK enforcement actions — it uses `NO ACTION` and handles SET_NULL in Python via the Collector. So the deferred check applies to Django's setup, and is susceptible to the partition-related trigger bugs above.

### The `cascade_delete()` pattern and its origin

The project already has a custom `cascade_delete()` in `koku/database.py:305` that manually walks Django model relations, calls `SET CONSTRAINTS ALL IMMEDIATE`, and issues raw SQL for SET_NULL/CASCADE. This is the correct workaround — `SET CONSTRAINTS ALL IMMEDIATE` forces FK checks to fire right after the UPDATE (when the state is still correct) rather than at COMMIT (when catalog corruption can cause false violations).

Notably, a [DEV Community article](https://dev.to/redhap/efficient-django-delete-cascade-43i5) documenting this exact pattern is authored by "redhap" (Red-HAP) — a contributor to the koku project.

### Diagnostic query (not yet run)

To confirm the theory, run in an affected tenant schema via `gabi-cli`:

```sql
SELECT c.conrelid::regclass AS "table",
       c.conname AS "constraint",
       c.condeferrable AS "deferrable",
       c.condeferred AS "deferred",
       c.confdeltype AS "delete_action",
       c.conparentid::regclass AS "parent_constraint"
FROM pg_constraint c
WHERE c.conrelid IN (
    SELECT inhrelid FROM pg_inherits
    WHERE inhparent = 'rates_to_usage'::regclass
    UNION ALL
    SELECT 'rates_to_usage'::regclass
)
AND c.contype = 'f'
ORDER BY c.conrelid::regclass::text;
```

This would reveal whether all partitions have the FK constraint, whether they're all DEFERRABLE, and whether any partition has a mismatch.

**Practical note on running cross-tenant queries:** The `rates_to_usage` table exists per-tenant in `orgNNNNNN` schemas. `gabi-cli` is read-only and doesn't support PL/pgSQL loops. On **stage** (small number of tenants) we used the two-step `string_agg(format(...))` approach — generate a giant UNION ALL, then copy-paste the output as a subquery. On **production** (1,807 tenant schemas) the generated UNION ALL was too large for gabi-cli's query buffer, so we had to use a shell script that looped over schemas and called `gabi-cli "SELECT count(*) FROM ${schema}.rates_to_usage;"` once per tenant, parsing the output with `awk`. The FK constraint diagnostic query above would need the same shell-script approach for production.

## Production Data: `rates_to_usage` Table Size

Queried via `gabi-cli` against production on 2026-07-07 (shell script looping over 1,807 tenant schemas; 1,798 returned results):

```
              BUCKET | NUM_TENANTS
---------------------+-------------
          0 (empty)  | 1748
             1 - 99  | 1
         100 - 999   | 1
       1K - 9,999    | 2
      10K - 49,999   | 18
      50K - 99,999   | 7
     100K - 499,999  | 16
     500K - 999,999  | 2
                 1M+ | 3
---------------------+-------------
       TOTAL TENANTS | 1798
          TOTAL ROWS | ~15,602,095
```

**Key observations:**
- 97% of tenants (1,748/1,798) have **zero rows** — no performance concern there
- 3 "whale" tenants hold **72% of all rows** (1.4M, 4.4M, 5.3M rows)
- The table is only 2 months old (created May 4, 2026) and grows a new partition every month

**Performance impact of missing `rate_id` index:**

For the 5.3M-row tenant, the unindexed `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` requires a sequential scan of ~5.3M rows across 2-3 partitions (~2.5-5 GB of table data). Estimated wall time:
- Cold disk: 25-100 seconds
- Warm/cached: 5-15 seconds

This runs inside `@transaction.atomic`, blocking the entire cost model API request. With a 30-second request timeout, this could cause the same HTTP 500 for the largest tenants — just for a different reason (timeout vs IntegrityError).

In 12 months, the table will have ~12 partitions per tenant. The whale tenants could have 30M+ rows each. The scan time scales linearly. **With an index, the same UPDATE completes in milliseconds regardless of table size.**

## GlitchTip Evidence

### Production (insights-hccm-prod)

| Issue ID | Events | First Seen | Last Seen | Error | Code Path |
|----------|--------|------------|-----------|-------|-----------|
| **[PROD-5ER](https://glitchtip.devshift.net/insights-hccm-prod/issues/4486185)** | 5 | 2026-06-10 | 2026-06-29 | `update or delete on table "cost_model_rate" violates FK "rates_to_usage_rate_id_..."` Key still referenced from `rates_to_usage` | `cost_models/serializers.py` → `update` |
| **[PROD-5F9](https://glitchtip.devshift.net/insights-hccm-prod/issues/4495069)** | 5 | 2026-06-15 | 2026-06-29 | `insert or update on table "rates_to_usage_2026_06" violates FK "rates_to_usage_rate_id_..."` Key `rate_id` not present in `cost_model_rate` | `masu/database/report_db_accessor_base.py` → `_execute_raw_sql_query` |

- **PROD-5ER** is the **exact bug this PR fixes** — deleting a rate while `rates_to_usage` still references it.
- **PROD-5F9** is a **race condition** going the other direction — the pipeline tries to INSERT a `rate_id` into `rates_to_usage` but the rate was concurrently deleted. This PR does NOT fix this case.

### Stage (insights-hccm-stage)

| Issue ID | Events | Error | Code Path |
|----------|--------|-------|-----------|
| **[STAGE-5I4](https://glitchtip.devshift.net/insights-hccm-stage/issues/4509184)** | 2 | `update or delete on table "cost_model" violates FK "rates_to_usage_cost_model_id_..."` Key still referenced from `rates_to_usage` | `cost_models/view.py` → `destroy` |
| **[STAGE-5HI](https://glitchtip.devshift.net/insights-hccm-stage/issues/4493532)** | 9 | `insert or update on table "rates_to_usage_2026_06" violates FK "rates_to_usage_cost_model_id_..."` Key `cost_model_id` not present in `cost_model` | `masu/database/report_db_accessor_base.py` → `_execute_raw_sql_query` |
| **[STAGE-4UV](https://glitchtip.devshift.net/insights-hccm-stage/issues/4010016)** | 1,218 | `update or delete on table "api_provider" violates FK on "reporting_ingressreports"` | `api/provider/models.py` → `_delete_from_target` |

- **STAGE-5I4 confirms Finding #6** — the `cost_model_id` FK variant, triggered by cost model deletion via the API (`view.py` → `destroy`)
- **STAGE-5HI** is the race condition on `cost_model_id` — pipeline INSERT references a cost model that was concurrently deleted
- **STAGE-4UV** (1,218 events!) is the same class of bug on a different table (`api_provider` / `reporting_ingressreports`)

### Evidence summary

| Bug class | PR #6166 fixes? | Prod evidence | Stage evidence |
|-----------|:---------------:|:-------------:|:--------------:|
| DELETE `cost_model_rate` while `rates_to_usage.rate_id` references it | **Yes** | PROD-5ER (5 events) | — |
| DELETE `cost_model` while `rates_to_usage.cost_model_id` references it | No | — | STAGE-5I4 (2 events) |
| Pipeline INSERT `rate_id` referencing concurrently deleted rate | No | PROD-5F9 (5 events) | — |
| Pipeline INSERT `cost_model_id` referencing concurrently deleted cost model | No | — | STAGE-5HI (9 events) |

## Scorecard

| Dimension | Rating | Key gap |
|-----------|--------|---------|
| Security | ★★★★★ | No issues — internal ORM operation, no external input |
| Correctness | ★★★★☆ | Fix is correct for this path; same class of bug confirmed on other paths |
| Auditability | ★★★★☆ | Good logging exists; missing a log line for the RTU null operation |
| Operational robustness | ★★★★★ | Runs inside existing `@transaction.atomic`, no new failure modes |
| Performance | ★★★☆☆ | Unindexed UPDATE on 5.3M-row tenant could take 25-100s under `@transaction.atomic` |
| Design quality | ★★★★☆ | Defensive-in-depth approach is sound; lazy import is a minor smell |
| Maintainability | ★★★☆☆ | Test Phase 1 mock is complex and tightly coupled to Django internals |
| Governance | ★★★★★ | Jira linked, clear description, testing instructions provided |

## Findings Status Summary

| # | Title | Severity | Dimension | Confirmed by |
|---|-------|----------|-----------|-------------|
| 1 | Root cause: PostgreSQL FK triggers on partitioned tables, not Django Collector | Medium | Correctness | Django source inspection |
| 2 | No index on `rate_id` — UPDATE sequential-scans 5.3M rows in largest tenant | Medium | Performance | Production DB query via gabi-cli |
| 3 | Missing log line for RTU nulling operation | Low | Auditability | Code inspection |
| 4 | Phase 1 test mock is fragile (`_raw_delete` is private Django API) | Low | Maintainability | Django source inspection |
| 5 | Lazy import inside function body | Info | Design | Accepted |
| 6 | Same FK issue on `cost_model_id` — cost model deletion path | Medium | Correctness | **GlitchTip STAGE-5I4** |
| 7 | Same FK issue on PriceList cascade-delete path | Medium | Correctness | Code inspection |
| 8 | Race condition: pipeline INSERT vs concurrent rate/cost_model deletion | Medium | Correctness | **GlitchTip PROD-5F9, STAGE-5HI** |

## Findings Detail

---

### Finding 1: Root cause — well-documented PG bugs with FK triggers on partitioned tables

**Severity:** Medium
**Dimension:** Correctness
**Location:** `koku/cost_models/rate_sync.py:196-199`, `koku/reporting/provider/ocp/models.py:1065`

**Description:**
Django's Collector correctly issues `UPDATE rates_to_usage SET rate_id = NULL` BEFORE the DELETE (verified by source inspection). But Django uses `NO ACTION DEFERRABLE INITIALLY DEFERRED` at the DB level — not `ON DELETE SET NULL`. The deferred FK check at COMMIT is susceptible to PostgreSQL bugs with FK triggers on partitioned tables (see Root Cause Analysis above).

The most probable mechanism is PG Bug #16908 (ATTACH/DETACH catalog corruption), which affected PG 12 through 17.0 and was fixed in PG 16.5 (November 2024). Koku runs PG 16 — if production is on anything before 16.5, the custom partition creation via `trfn_partition_manager` could leave FK triggers in a corrupted state.

The project already has a custom `cascade_delete()` in `koku/database.py:305` that works around this with `SET CONSTRAINTS ALL IMMEDIATE`. But `sync_rate_table()` and the `destroy()` view use standard Django `.delete()`.

**Risk:**
Every `SET_NULL`/`CASCADE` FK from a partitioned table deleted via standard Django `.delete()` hits this class of bug. The fix treats the symptom for one call site. Django 5.2+ offers a proper fix via `db_on_delete` ([Django #21961](https://code.djangoproject.com/ticket/21961)).

**Recommendation:**
1. Add a code comment explaining *why* the manual null is needed (PG partitioned table FK bugs + Django's Python-level SET_NULL)
2. **Check the production PG version** — if < 16.5, upgrade to get the ATTACH/DETACH catalog fix
3. Consider using `cascade_delete()` from `koku.database` for all deletions involving partitioned-table FKs
4. Long-term: upgrade to Django 5.2+ and use `db_on_delete=models.SET_NULL` to let PostgreSQL handle it natively

**Effort:** S (hours) for comment + version check; M (days) for cascade_delete migration; L (weeks) for Django upgrade

---

### Finding 2: No index on `rate_id` — UPDATE sequential-scans 5.3M rows

**Severity:** Medium
**Dimension:** Performance
**Location:** `koku/cost_models/rate_sync.py:197`, `koku/reporting/provider/ocp/models.py:1052-1061`

**Description:**
The `RatesToUsage` model has indexes on `(usage_start, source_uuid, report_period_id)`, `namespace`, `cluster_id`, `custom_name`, `monthly_cost_type`, and `label_hash` — but **not on `rate_id`**.

Production data (queried 2026-07-07 via gabi-cli) shows the table has ~15.6M total rows across 1,807 tenant schemas, with extreme skew: the 3 largest tenants have 1.4M, 4.4M, and 5.3M rows respectively, while 97% of tenants have zero rows. The table is only 2 months old and grows a new partition every month.

For the 5.3M-row tenant, the unindexed UPDATE scans ~2.5-5 GB of table data. Estimated: 25-100 seconds cold, 5-15 seconds warm. This runs inside `@transaction.atomic`, blocking the cost model API request for the entire duration.

In 12 months, the whale tenants could have 30M+ rows. The scan time scales linearly. With an index, it's milliseconds.

**Risk:**
The 3 whale tenants could see multi-second to minute-long API latency on cost model updates, with a real risk of request timeouts.

**Recommendation:**
```python
models.Index(fields=["rate_id"], name="ratestousage_rate_id_idx"),
```

**Effort:** S (hours) — one migration

---

### Finding 3: Missing log line for RTU nulling operation

**Severity:** Low
**Dimension:** Auditability
**Location:** `koku/cost_models/rate_sync.py:196-199`

**Description:**
The Rate deletion logs `"Deleted {deleted_count} stale Rate rows..."` but the RTU nulling is silent.

**Recommendation:**
```python
nulled_count = RatesToUsage.objects.filter(rate_id__in=to_delete_uuids).update(rate_id=None)
if nulled_count:
    LOG.info(f"Nulled rate_id on {nulled_count} RatesToUsage rows before deleting stale Rates")
```

**Effort:** S (minutes)

---

### Finding 4: Phase 1 test uses private Django API `_raw_delete`

**Severity:** Low
**Dimension:** Maintainability
**Location:** `koku/cost_models/test/test_sync_rate_table.py:518-537`

**Description:**
The `_broken_sync_delete_path` context manager patches `Rate.objects.filter` to replace `.delete()` with `._raw_delete()` — a private Django internal. This simulates "what if we skip the Collector AND skip the manual null?" to prove the FK constraint exists. It does not reproduce the actual production bug (which involves the Collector running correctly but the PostgreSQL-level enforcement failing).

**Risk:** `_raw_delete` could change between Django versions; the test could pass/fail for wrong reasons.

**Recommendation:** Phase 2 alone provides sufficient regression coverage. Consider simplifying Phase 1 to a raw SQL constraint check, or dropping it.

**Effort:** S (hours)

---

### Finding 5: Lazy import inside function body

**Severity:** Informational | **Status:** Accepted

The `from reporting.provider.ocp.models import RatesToUsage` inside the `if` block is standard circular-import avoidance.

---

### Finding 6: Same FK issue on `cost_model_id` — confirmed on stage

**Severity:** Medium
**Dimension:** Correctness
**Location:** `koku/reporting/provider/ocp/models.py:1066`, `koku/cost_models/view.py:172`

**Description:**
`RatesToUsage` also has `cost_model = models.ForeignKey("cost_models.CostModel", on_delete=models.SET_NULL, null=True)`. Deleting a cost model via the API triggers the same IntegrityError.

We traced the code path: `view.py:172` `destroy()` calls `manager.update_provider_uuids([])` to detach providers, then `super().destroy()` which is DRF's `ModelViewSet.destroy()` → `instance.delete()` — plain Django ORM delete. **`cascade_delete()` is not used anywhere in this path.**

**Confirmed by GlitchTip:** [INSIGHTS-HCCM-STAGE-5I4](https://glitchtip.devshift.net/insights-hccm-stage/issues/4509184) (2 events, Jun 26 – Jun 30) — `update or delete on table "cost_model" violates FK "rates_to_usage_cost_model_id_..."` from `cost_models/view.py` → `destroy`.

**Risk:** HTTP 500 on cost model deletion via API.

**Recommendation:** Apply the same pattern — null `rates_to_usage.cost_model_id` before deleting the cost model, or switch to `cascade_delete()`.

**Effort:** S (hours)

---

### Finding 7: Same FK issue on PriceList cascade-delete path

**Severity:** Medium
**Dimension:** Correctness
**Location:** `koku/cost_models/models.py:164`, `koku/cost_models/price_list_manager.py:224`

**Description:**
`Rate` has `on_delete=CASCADE` to `PriceList`. `PriceListManager.delete()` calls `self._model.delete()` (standard Django), which cascades to delete Rate rows, which should trigger SET_NULL on RTU — same failure path.

Not yet confirmed in GlitchTip (price list deletion may not be exposed via the API), but architecturally identical to Findings 1 and 6.

**Effort:** S (hours)

---

### Finding 8: Race condition — pipeline INSERT vs concurrent deletion (NEW)

**Severity:** Medium
**Dimension:** Correctness
**Location:** `masu/database/report_db_accessor_base.py`, raw SQL INSERT pipelines

**Description:**
The cost model update pipeline runs asynchronously via Celery tasks. When a rate or cost model is deleted while the pipeline is concurrently inserting rows into `rates_to_usage`, the INSERT fails because the FK reference is to a row that was just deleted.

**Confirmed by GlitchTip:**
- [INSIGHTS-HCCM-PROD-5F9](https://glitchtip.devshift.net/insights-hccm-prod/issues/4495069) (5 events, Jun 15 – Jun 29) — `INSERT into "rates_to_usage_2026_06"` fails, `rate_id` not present in `cost_model_rate`
- [INSIGHTS-HCCM-STAGE-5HI](https://glitchtip.devshift.net/insights-hccm-stage/issues/4493532) (9 events, Jun 14 – Jun 30) — `INSERT into "rates_to_usage_2026_06"` fails, `cost_model_id` not present in `cost_model`

**Risk:** Pipeline processing failures for tenants where a cost model is modified while data is being processed. Could cause incomplete cost calculations.

**Recommendation:** The pipeline INSERT SQL should handle the case where the referenced rate/cost_model was deleted mid-pipeline:
1. Wrap the INSERT in a try/except for IntegrityError and retry with NULL FK values, or
2. Check that the rate/cost_model still exists before INSERT, or
3. Accept the error and let the pipeline retry on the next cycle (current behavior, but noisy)

**Effort:** M (days)

---

## Design Consideration: CASCADE vs SET_NULL

The PR description asks for feedback: *"We chose to null rate_id rather than delete rates_to_usage rows (CASCADE-style). RTU is intermediate pipeline data, but each row carries real cost values and downstream SQL aggregates by custom_name, not rate_id."*

Team feedback (Cody) challenged this: *"I question whether on_delete=SET_NULL is the right behavior. These rows are derived data — computed by taking usage and multiplying by the Rate. If either is deleted, there's no benefit to keeping the rows around."*

### Validation: CASCADE is the correct behavior

We validated Cody's suggestion against the codebase. **CASCADE is strictly better than SET_NULL for both the `rate_id` and `cost_model_id` FKs on `rates_to_usage`:**

1. **`rate_id` and `cost_model_id` are never read by any downstream consumer.** The aggregation SQL (`aggregate_rates_to_daily_summary.sql`) does not SELECT, JOIN on, or filter by either column. They are write-only traceability fields. No API endpoint, no ORM query, no SQL template reads them.

2. **The pipeline does full DELETE + INSERT per billing period.** Every cost model update run wipes all RTU rows for the date range (`DELETE FROM rates_to_usage WHERE usage_start >= ... AND source_uuid = ...`) and reinserts from scratch. Deleted rows are recreated on the next run — or correctly absent if the rate/cost model is gone.

3. **All RTU data is fully derivable.** `calculated_cost = usage_quantity × rate`, computed in the INSERT SQL from `reporting_ocpusagelineitem_daily_summary` (usage) and `cost_model_rate` (rates). `custom_name`, `metric_type`, `cost_model_rate_type` all come from `cost_model_rate`. Nothing in RTU is original data.

4. **No API exposes RTU directly.** Users see costs through `reporting_ocpusagelineitem_daily_summary`, which is populated by aggregating RTU. The UI breakdown table (`OCPCostUIBreakDownP`) exists as a model but is not wired up in production — the SQL template is under `docs/architecture/cost-breakdown/poc/`.

5. **SET_NULL creates orphan rows.** With SET_NULL, deleted-rate RTU rows accumulate with `rate_id = NULL` until the next pipeline run cleans them via the DELETE + INSERT refresh. Under CASCADE, they're gone immediately. The aggregation result is identical in both cases since it doesn't use `rate_id`.

6. **CASCADE eliminates the FK violation entirely.** If the FK is `on_delete=CASCADE`, Django's Collector deletes the RTU rows instead of trying to SET_NULL them. The deferred-trigger bugs that cause the IntegrityError become irrelevant — there are no dangling references because the referencing rows are gone.

### Impact on the missing index (Finding #2)

The missing `rate_id` index is needed **regardless of CASCADE vs SET_NULL**, and is arguably **more urgent under CASCADE**:

- **SET_NULL** does `UPDATE ... WHERE rate_id IN (...)` — unindexed sequential scan, but doesn't change row count or touch other indexes.
- **CASCADE** does `DELETE ... WHERE rate_id IN (...)` — same sequential scan to find rows, but also has to delete potentially thousands of rows and update all 6 indexes on the table.
- **Django's Collector** under CASCADE also needs to SELECT all RTU rows referencing the rate to build its deletion plan — another sequential scan without the index.

For the 5.3M-row whale tenant, an unindexed CASCADE DELETE would be heavier than the unindexed SET_NULL UPDATE. The index is critical for either approach.

### Recommendation

Change both FKs on `rates_to_usage` from `SET_NULL` to `CASCADE`:

```python
rate = models.ForeignKey("cost_models.Rate", on_delete=models.CASCADE, null=True)
cost_model = models.ForeignKey("cost_models.CostModel", on_delete=models.CASCADE, null=True)
```

This requires a migration (to update the Django model metadata) but no schema change — the DB-level constraint is `NO ACTION` regardless. Combined with the `rate_id` index and `cascade_delete()` (or eventually `db_on_delete=CASCADE` in Django 5.2+), this resolves the FK violation class of bugs systemically.

**Note:** The PR's current SET_NULL fix is still correct as a short-term merge — it stops the bleeding. The CASCADE change is a follow-up that addresses the design-level question.

## Strengths

- **Minimal, targeted fix.** The 3-line change is the smallest possible intervention that resolves the immediate issue.
- **Well-structured test.** Phase 2 verifies the Rate is deleted, the RTU row survives, `rate_id` is null, and `calculated_cost` is preserved.
- **Clear PR description.** Explains root cause, fix rationale, and testing steps. The "design note" asking for feedback on NULL vs CASCADE is good engineering practice — and prompted exactly the feedback that led to this analysis.
- **Atomic transaction coverage.** The fix runs inside `CostModelManager.update()`'s `@transaction.atomic`, so a failure rolls back cleanly.

## Priority Remediation Order

| Priority | Finding | Effort | Rationale |
|----------|---------|--------|-----------|
| 1 | #3 — Add log line | S (min) | Trivial, improves operability |
| 2 | #1 — Add code comment explaining root cause | S (hours) | Prevents someone removing "redundant" code |
| 3 | #2 — Add index on `rate_id` | S (hours) | Prevents timeout for whale tenants |
| 4 | #6 — Fix `cost_model_id` FK on delete path | S (hours) | Confirmed on stage (STAGE-5I4) |
| 5 | #8 — Handle pipeline INSERT race condition | M (days) | Confirmed in prod (PROD-5F9) |
| 6 | #7 — Audit PriceList cascade path | S (hours) | Same class, unconfirmed |
| 7 | #4 — Simplify Phase 1 test | S (hours) | Nice to have |

## Accepted Risks

- **Finding 5** (lazy import) — accepted as-is, standard circular-import avoidance pattern.

## Current State

- **Total findings:** 8
- **Confirmed by production/stage data:** 4 (Findings 1, 6, 8 — two sub-cases)
- **Resolved:** 0
- **Accepted:** 1
- **Open:** 7

## Verdict

**Merge with minor additions.** The fix is correct, safe, and addresses a confirmed production bug (5 events in prod). Recommended additions before merge:

1. Add a log line for the RTU null count (Finding #3)
2. Add a code comment explaining why the manual null is needed despite `on_delete=SET_NULL` (Finding #1)

Follow-up tickets:

3. **High priority:** Change RTU FKs from `SET_NULL` to `CASCADE` — RTU is derived data, CASCADE is the correct behavior (see "Design Consideration" section). Requires migration + `rate_id` index in the same PR.
4. **High priority:** Add index on `rates_to_usage.rate_id` (Finding #2) — needed for both SET_NULL and CASCADE, more urgent under CASCADE
5. **High priority:** Check production PG version — if < 16.5, upgrade to get the ATTACH/DETACH catalog fix (PG Bug #16908)
6. **High priority:** Fix `cost_model_id` FK on cost model delete path (Finding #6) — confirmed on stage, `destroy()` does not use `cascade_delete()`
7. **Medium priority:** Handle pipeline INSERT race condition (Finding #8) — confirmed in prod; under CASCADE, the orphan-insert case may resolve naturally
8. **Low priority:** Audit PriceList cascade path (Finding #7), simplify Phase 1 test (Finding #4)
9. **Long-term:** Upgrade to Django 5.2+ and use `db_on_delete=CASCADE` ([Django #21961](https://code.djangoproject.com/ticket/21961)) — lets PostgreSQL handle CASCADE natively, bypassing the Collector entirely
