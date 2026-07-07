# Adversarial Due Diligence Review — PR #6166: COST-7736 FK Violation Fix

## Version & Date
Version: 2.0 | Date: 2026-07-07 | Reviewer: AI-assisted

## Executive Summary

This PR fixes an HTTP 500 (`IntegrityError`) that occurs when updating a cost model to remove a rate that has existing `rates_to_usage` rows referencing it. The fix is a 3-line addition to `sync_rate_table()` that explicitly nulls `rates_to_usage.rate_id` before deleting stale `Rate` rows. A 97-line regression test is included.

The fix is **correct and resolves the immediate production issue** — confirmed by GlitchTip data showing 5 occurrences in production (INSIGHTS-HCCM-PROD-5ER, last seen June 29, 2026). However, the review uncovered a broader class of the same bug affecting other FK paths, also confirmed by production and stage error data.

**Key findings from deep investigation:**

1. **Django's Collector should handle this automatically** — tracing through Django 4.2's `deletion.py` confirms the Collector correctly discovers the `RatesToUsage` relation, issues SET_NULL UPDATEs before DELETEs, and does not use fast-delete for this case. The failure mechanism is at the PostgreSQL level, not Django's.

2. **The `rates_to_usage` table is a partitioned table with ~15.6M rows in production** — heavily skewed across 1,807 tenant schemas (3 tenants hold 72% of all rows, 97% of tenants have zero rows). The table was introduced May 4, 2026 (PR #6017) and grows monotonically.

3. **GlitchTip confirms the same class of bug on multiple FK paths** — not just `rate_id` (which this PR fixes) but also `cost_model_id` on the delete path, and a race condition between pipeline INSERTs and concurrent deletions.

4. **No index exists on `rate_id`** — the fix's UPDATE will sequential-scan every partition in the largest tenants (5.3M rows in the biggest), potentially causing multi-second API latency under `@transaction.atomic`.

## Root Cause Analysis

### What Django does (verified by source inspection)

We traced through Django 4.2's deletion code in the project's virtualenv (`.venv/lib/python3.11/site-packages/django/db/models/deletion.py`):

1. **`get_candidate_relations_to_delete()`** (line 84-91) — calls `opts.get_fields(include_hidden=True)` and filters for auto-created reverse relations. The `RatesToUsage.rate` FK creates a `ManyToOneRel` on `Rate._meta` that satisfies all conditions. **The Collector sees the relation.**

2. **`can_fast_delete()`** (line 185-227) — checks whether ALL reverse FK relations use `DO_NOTHING` (line 214-219). Since `RatesToUsage.rate` uses `SET_NULL`, this returns `False`. **Rate objects are NOT fast-deleted.**

3. **`collect()`** (line 309) — because `SET_NULL.lazy_sub_objs = True` (line 343-345), the SET_NULL handler stores a lazy queryset in `field_updates` without evaluating it.

4. **`delete()`** execution order — `fast_deletes` first (line 466), then `field_updates` / SET_NULL UPDATEs (line 472), then instance DELETEs (line 498). **SET_NULL runs BEFORE the DELETE.**

5. **django-tenants does not interfere** — both `cost_models` and `reporting` are in `TENANT_APPS` (`settings.py:111`), so both tables exist in the same tenant schema. The `TenantSyncRouter` only implements `allow_migrate`, not `db_for_read`/`db_for_write`.

**Conclusion:** Django's Collector correctly issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` before `DELETE FROM cost_model_rate WHERE uuid IN (...)`. At the Python/ORM level, nothing is wrong.

### What happens at the PostgreSQL level

The critical discovery: **Django does NOT create `ON DELETE SET NULL` at the database level.** The DB-level FK constraint is:

```sql
FOREIGN KEY (rate_id) REFERENCES cost_model_rate(uuid) DEFERRABLE INITIALLY DEFERRED
```

No `ON DELETE SET NULL` clause. The database default is `ON DELETE NO ACTION`. Django handles SET_NULL purely in Python. The database only enforces "don't allow commits with dangling FK references."

So the sequence should be:
1. Collector issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` — PostgreSQL routes to all partitions
2. Collector issues `DELETE FROM cost_model_rate WHERE uuid IN (...)` — succeeds
3. At COMMIT, deferred FK trigger checks whether any `rates_to_usage` rows still reference deleted UUIDs
4. They shouldn't, because step 1 already nulled them → **no error expected**

Yet the error occurs. The exact failure mechanism remains unconfirmed without running diagnostic SQL against the production database. The most probable cause is a PostgreSQL bug with FK enforcement triggers on partitioned tables — PostgreSQL has documented bugs where:
- FK constraints aren't properly cloned to new partitions at lower levels (PG 12.2)
- `ENABLE/DISABLE TRIGGER` fails on partitioned FK triggers (PG 15.3)
- ATTACH/DETACH PARTITION commands fail to correctly convert FK trigger catalog entries (PG 16.5/15.9/14.14/13.17)

This project uses a custom trigger-based partition creation system (`trfn_partition_manager` via `partitioned_tables` tracking table), which adds another layer where FK triggers could be improperly propagated to new partitions.

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

## Production Data: `rates_to_usage` Table Size

Queried via `gabi-cli` against production on 2026-07-07:

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

### Finding 1: Root cause is at the PostgreSQL level, not Django's Collector

**Severity:** Medium
**Dimension:** Correctness
**Location:** `koku/cost_models/rate_sync.py:196-197`, `koku/reporting/provider/ocp/models.py:1065`

**Description:**
We traced through Django 4.2's `deletion.py` and confirmed that the Collector correctly:
- Discovers the `RatesToUsage` relation via `Rate._meta.related_objects`
- Rejects fast-delete because `RatesToUsage.rate` uses `SET_NULL` (not `DO_NOTHING`)
- Issues `UPDATE rates_to_usage SET rate_id = NULL WHERE rate_id IN (...)` BEFORE the DELETE

Django does NOT create `ON DELETE SET_NULL` at the database level. The DB constraint is `REFERENCES ... NO ACTION DEFERRABLE INITIALLY DEFERRED`. Django handles SET_NULL purely in Python. The database only enforces "no dangling references at COMMIT."

Despite the Collector correctly issuing the UPDATE, the IntegrityError still occurs in production (PROD-5ER, 5 events). The most probable cause is a PostgreSQL bug with FK enforcement triggers on partitioned tables — either the trigger's internal state is stale after partition management operations, or the constraint wasn't properly cloned to a new partition.

The project already has a custom `cascade_delete()` in `koku/database.py:305` that handles this pattern manually with `SET CONSTRAINTS ALL IMMEDIATE`. But `sync_rate_table()` uses standard Django `.delete()`.

**Risk:**
Every future `SET_NULL` or `CASCADE` FK from a partitioned table that is deleted via standard Django `.delete()` will hit the same class of bug. The fix treats the symptom for this one call site.

**Recommendation:**
1. Add a code comment explaining *why* the manual null is needed despite `on_delete=SET_NULL`
2. Consider using `cascade_delete()` from `koku.database` for Rate deletions
3. Run the diagnostic SQL query (above) to confirm the exact PostgreSQL-level mechanism

**Effort:** S (hours) for comment; M (days) for diagnostic + cascade_delete evaluation

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
**Location:** `koku/cost_models/rate_sync.py:196-197`

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
**Location:** `koku/cost_models/test/test_sync_rate_table.py:515-536`

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
**Location:** `koku/reporting/provider/ocp/models.py:1066`, `koku/cost_models/view.py`

**Description:**
`RatesToUsage` also has `cost_model = models.ForeignKey("cost_models.CostModel", on_delete=models.SET_NULL, null=True)`. Deleting a cost model via the API triggers the same IntegrityError.

**Confirmed by GlitchTip:** [INSIGHTS-HCCM-STAGE-5I4](https://glitchtip.devshift.net/insights-hccm-stage/issues/4509184) (2 events, Jun 26 – Jun 30) — `update or delete on table "cost_model" violates FK "rates_to_usage_cost_model_id_..."` from `cost_models/view.py` → `destroy`.

**Risk:** HTTP 500 on cost model deletion via API.

**Recommendation:** Apply the same pattern — null `rates_to_usage.cost_model_id` before deleting the cost model, or switch to `cascade_delete()`.

**Effort:** S (hours)

---

### Finding 7: Same FK issue on PriceList cascade-delete path

**Severity:** Medium
**Dimension:** Correctness
**Location:** `koku/cost_models/models.py:164`, `koku/cost_models/price_list_manager.py:216`

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

## Strengths

- **Minimal, targeted fix.** The 3-line change is the smallest possible intervention that resolves the issue.
- **Correct design choice.** Nulling `rate_id` rather than deleting RTU rows preserves historical cost data (`calculated_cost`, `custom_name`) that downstream SQL aggregates depend on.
- **Well-structured test.** Phase 2 verifies the Rate is deleted, the RTU row survives, `rate_id` is null, and `calculated_cost` is preserved.
- **Clear PR description.** Explains root cause, fix rationale, and testing steps. The "design note" asking for feedback on NULL vs CASCADE is good engineering practice.
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

3. **High priority:** Add index on `rates_to_usage.rate_id` (Finding #2) — prevents timeout for whale tenants
4. **High priority:** Fix `cost_model_id` FK on cost model delete path (Finding #6) — confirmed on stage
5. **Medium priority:** Handle pipeline INSERT race condition (Finding #8) — confirmed in prod
6. **Low priority:** Audit PriceList cascade path (Finding #7), simplify Phase 1 test (Finding #4)
