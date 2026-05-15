# Risk Register

Consolidated risk register, decision rationales, and mitigation plans for
the cost breakdown feature ([COST-7249](https://redhat.atlassian.net/browse/COST-7249)).

This document is the single source of truth for risk tracking. Other
design documents link here for details.

---

## Risk Summary

| ID | Risk | Status | Phase | One-line mitigation |
|----|------|--------|-------|---------------------|
| R1 | 6 entangled CPU cost components | **MITIGATED** | 2 | All 6 map 1:1 to distinct rate metrics (OQ-1). |
| R2 | Aggregation produces different values than direct-write | Active | 2 | CI validation query + Phase 2 benchmarks. |
| R3 | Row explosion in `RatesToUsage` | Active | 2 | 12x multiplier quantified; benchmarks #1, #2, #7, #8. |
| R4 | Monthly cost rates produce more rows than expected | **MITIGATED** | 3 | GROUP BY quantified (OQ-2). |
| R5 | Cost category reclassification invalidates breakdown tree | **MITIGATED** | 4 | Existing `update_summary_tables` chain handles it (OQ-4). |
| R6 | 25 SQL file modifications introduce regressions | Active | 3 | Per-file-per-PR + 8-point checklist. |
| R7 | Dual-write divergence (JSON ↔ Rate table) | Active | 1-4 | Delete-all + recreate on every write. |
| R8 | `custom_name` migration produces ugly names | Active | 1 | Acceptable per PRD; users can rename. |
| R9 | Frontend tab restructure breaks workflows | Active | 4 | Usage cards move to adjacent tab, not removed. |
| R10 | Trino SQL dialect issues | Active | 3 | Test with Trino locally. |
| R11 | Concurrent cost model updates create duplicate rows | Active | 2-3 | Redis lock + DELETE-before-INSERT. |
| R12 | `CostModelManager.update()` missing `@transaction.atomic` | Active | 1 | Add `@transaction.atomic`. |
| R13 | JSONB JOIN performance in aggregation | **MITIGATED** | 2 | `label_hash` column replaces JSONB GROUP BY. |
| R14 | Back-allocation rounding | **N/A** | — | Eliminated by IQ-9 Option 1. |
| R15 | Back-allocation JOIN complexity | **REPLACED** | 4 | Replaced by simpler RTU × daily summary JOIN. |
| R16 | Aggregation GROUP BY granularity mismatch | Active | 2 | `resource_id` confirmed absent from GROUP BY. |
| R17 | Markup ORM overhead | **MITIGATED** | 2 | ORM-first + SQL fallback if >30s. |
| R18 | Distribution SQL rewrite regression | Active | 4 | Old files preserved for rollback; existing integration tests sufficient per tech lead. |
| R19 | Aggregation handling of `distributed_cost` | **RESOLVED** | 4 | Aggregation sums both `calculated_cost` and `distributed_cost` (Option A). |
| R20 | Aggregation DELETE scope too broad for Phase 2 partial deployment | **MITIGATED** | 2 | Reorder orchestration: aggregation runs before legacy VM/tag direct-write paths (Option D). |
| R21 | Transitional VM cost handling during Phase 2 → Phase 3 gap | **MITIGATED** | 2-3 | Resolved by R20 Option D + existing `_update_vm_usage_costs()` split from `_update_usage_costs()`. |

---

## R2/R3 — Aggregation Correctness and Row Explosion

### Decision: DELETE + INSERT aggregation

The aggregation step replaces `usage_costs.sql` direct-write. Three
possible patterns were evaluated:

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | **UPDATE existing rows** | No new rows created. | `usage_costs.sql` creates new rows with `uuid_generate_v4()`; there are no pre-existing rows to UPDATE. | **Rejected** |
| B | **DELETE + INSERT** | Matches `usage_costs.sql` pattern exactly. Downstream sees same row structure. | Two SQL statements per cycle. DELETE can be expensive. | **Selected** |
| C | **UPSERT (ON CONFLICT)** | Single statement. | Daily summary has no unique constraint on rate-type rows. 8-column unique index would be invasive. | **Rejected** |

### Phase 2 Benchmarking Plan

**Test configuration**: 30 rate types, 100 namespaces, 1000 nodes,
30 days, varying `pod_labels` cardinality.

Thresholds derived from koku's existing performance envelope (current
`usage_costs.sql` < 60s for largest tenants; new pipeline adds INSERT +
aggregation = 2× budget).

| # | Benchmark | Acceptance Criteria | Risk |
|---|-----------|---------------------|------|
| 1 | `RatesToUsage` row count/month | < 100M rows | R3 |
| 2 | `insert_usage_rates_to_usage.sql` time | < 60s per (source, rate_type, range) | R3 |
| 3 | `aggregate_rates_to_daily_summary.sql` time | < 30s per (source, range) | R2, R13 |
| 4 | CI validation query: zero diff rows | All diffs = 0 (NUMERIC precision) | R2 |
| 5 | `label_hash` index effectiveness | EXPLAIN ANALYZE shows index scan | R13 |
| 6 | Markup ORM processing time | < 30s; switch to SQL fallback if exceeded | R17 |
| 7 | End-to-end cost model update | < 5 min per source | R2, R3 |
| 8 | Partition size on disk | < 2 GB per monthly partition | R3 |

**If any fails**: Investigate before Phase 3. Key levers: reduce
`pod_labels` cardinality via hash-based grouping, optimize indexes,
or drop raw JSONB from GROUP BY.

---

## R6 — SQL File Modification Regressions

### Decision: Per-file-per-PR with 8-point checklist

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | Single large PR | Ships Phase 3 in one merge. | 75 file changes; impossible to review thoroughly. Rollback is all-or-nothing. | **Rejected** |
| B | Per-path batches | 3 PRs. | Still 8-9 files per PR; regression isolation is coarse. | Viable but coarse |
| C | Per-file-per-PR | Small, reviewable, surgically revertable. | 25 PRs. | **Selected** |
| D | Grouped by cost type | Logical grouping, 4-5 PRs. | Mixes execution engines; harder to isolate path-specific issues. | **Rejected** |

### 8-Point Checklist

| # | Check | How |
|---|-------|-----|
| 1 | `RatesToUsage` INSERT row count | `SELECT COUNT(*)` with known config |
| 2 | `custom_name` correct | Spot-check first 10 rows |
| 3 | `metric_type` correct | `SELECT DISTINCT metric_type` |
| 4 | `calculated_cost` matches daily summary | CI validation query |
| 5 | `label_hash` populated | `SELECT COUNT(*) WHERE label_hash IS NULL` = 0 |
| 6 | Aggregation output unchanged | Compare daily summary totals before/after |
| 7 | Trino dialect | Run against Trino-enabled dev environment |
| 8 | Self-hosted uses PostgreSQL syntax | Run against PostgreSQL directly |

**Ordering**: PostgreSQL first, then Trino, then self-hosted. Tag-rate
files before monthly-cost files.

---

## R11 — Concurrent Cost Model Updates

### Decision: Single DELETE per window

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | Per-rate-type DELETE | Matches koku convention; allows partial recalc. | Order-of-operations risk; 5+ DELETE statements. | **Rejected** |
| B | Single DELETE per window | Simple, safe, atomic. | Cannot partially recalculate. | **Selected** |
| C | UPSERT (ON CONFLICT) | Idempotent. | No viable unique key (JSONB columns). | **Rejected** |

---

## R13 — JSONB JOIN Performance (`label_hash`)

### Problem

Aggregation and CI validation need to GROUP BY / JOIN on three JSONB
columns (`pod_labels`, `volume_labels`, `all_labels`). JSONB equality
is O(document size) per comparison — expensive on millions of rows.
This is a production hot path (every cost model recalculation).

### Decision: Computed `label_hash` column

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | GIN indexes | Standard PostgreSQL JSONB pattern. | GIN does not support equality (`=`); useless for GROUP BY. | **Rejected** |
| B | B-tree indexes | Supports equality. | Still O(document size) per comparison. Three separate indexes don't combine for multi-column GROUP BY. | **Rejected** |
| C | Hash indexes | Equality-only, WAL-logged since v10. | No multi-column keys. Hash computed on full value at query time. | **Rejected** |
| D | Computed `label_hash` (md5) | Fixed 32-char VARCHAR. O(1) comparison. Computed at INSERT time. | Extra column + index. md5 collision risk (see below). | **Selected** |
| E | Accept the cost, benchmark first | Zero complexity. | If slow, blocks production. Retrofitting requires data migration. | **Rejected** |

### Why Option D

1. Single 32-byte comparison replaces three variable-size JSONB documents.
2. md5 computed once at INSERT time; aggregation only compares 32-char strings.
3. B-tree on `VARCHAR(32)` is compact and cache-efficient.
4. JSONB columns stay for data access / debugging.
5. Koku precedent: computed columns used elsewhere (`cluster_alias`, `all_labels`).
6. Cheap to add now; expensive to retrofit after Phase 2.

### Hash collision risk

md5 = 128-bit hash. Birthday paradox probability for 100M distinct
combinations: ~10⁻²² (effectively zero). Detectable by CI validation
query. Can widen to `sha256` / `VARCHAR(64)` if preferred.

### Computation

```sql
md5(COALESCE(pod_labels::text, '')
    || COALESCE(volume_labels::text, '')
    || COALESCE(all_labels::text, ''))
```

---

## R17 — Markup ORM Overhead

### Decision: ORM-first with SQL fallback

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | SQL-only | Single query, fastest. | Changes existing ORM pattern; harder to test. | Viable but higher risk |
| B | ORM-only | Consistent with markup pattern. | May not scale for >100K rows. | Viable but may not scale |
| C | ORM-first, SQL fallback | Ships faster; fallback pre-designed. | Two implementations. | **Selected** |

SQL fallback (`insert_markup_rates_to_usage.sql`) is pre-designed in
[sql-pipeline.md](./sql-pipeline.md#markup--ratestousage-step-2).
Phase 2 benchmark #6 triggers switch if ORM > 30s.

---

## R18 — Distribution SQL Rewrite Regression

**Status**: Active (Phase 4) — mitigation confirmed by tech lead

5 new distribution SQL files replace the existing `distribute_*.sql`
files. Old files preserved for rollback (code revert, no Unleash flag).

### Regression test approach

1. Run **old** distribution SQL on a test dataset → capture
   `SUM(distributed_cost)` per (namespace, day, distribution_type).
2. Run **new** per-rate distribution SQL on the same dataset → capture
   `SUM(distributed_cost)` per (namespace, day, distribution_type)
   from `RatesToUsage`.
3. Compare: totals must match within NUMERIC(33,15) precision.
4. Per-rate drill-down: verify that individual per-rate distributed
   rows sum to the aggregated `distributed_cost` for each namespace.

### Acceptance criteria

Per tech lead: existing integration tests that check distribution
amounts on the daily summary table are sufficient to confirm no
regressions. No separate CI gate or staging dataset comparison needed.

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | Aggregate `distributed_cost` per (namespace, day, type) | Old vs new diff = 0 within NUMERIC(33,15) precision |
| 2 | Per-rate distributed rows sum to namespace total | SUM(per-rate) = aggregated `distributed_cost` per namespace |
| 3 | No orphaned distributed rows | Every distributed row traces back to a valid `RatesToUsage` source row |
| 4 | Zero-cost namespaces | Namespaces with `calculated_cost = 0` produce zero distributed rows (no divide-by-zero) |
| 5 | Single-node clusters | Distribution degenerates correctly (100% to the single node) |
| 6 | GPU distribution | GPU rates distribute by GPU-specific metrics, not CPU/memory |
| 7 | Execution time | New per-rate distribution ≤ 2× old distribution time per (source, date range) |

### Orchestration phasing note

The target orchestration order (distribution before aggregation) applies
from **Phase 4 onward**. During Phases 2-3, the legacy ordering is
preserved: `RatesToUsage INSERT → aggregate → distribute (on daily
summary) → UI summary`. Phase 4 rewires to: `RatesToUsage INSERT →
raw cost → distribute (on RatesToUsage) → aggregate → UI summary`.

---

## R19 — Aggregation Handling of `distributed_cost`

**Status**: **RESOLVED** — Option A adopted per tech lead direction

### Problem

With IQ-9 Option 1, distribution writes per-rate distributed rows
back to `RatesToUsage` with a `distributed_cost` column. The
aggregation SQL (`aggregate_rates_to_daily_summary.sql`) needs to
populate `distributed_cost` on the daily summary for UI summary
tables and the Sankey chart.

### Decision: Option A — Aggregation sums both columns

The aggregation SQL is extended to `SUM(COALESCE(rtu.distributed_cost, 0))`
alongside the existing `calculated_cost` SUMs. This keeps a single write
path to the daily summary, consistent with the single-source-of-truth
principle.

Existing integration tests that verify distribution amounts on the daily
summary table confirm no regressions — no additional test infrastructure
needed.

### Options evaluated

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | **Aggregation sums both** | Single write path. Consistent with single-source-of-truth. | Aggregation SQL slightly more complex. | **Selected** |
| B | **Distribution dual-writes** | Aggregation SQL unchanged. | Two write targets; dual-path concern. | Rejected |

---

## Risk × Phase Matrix

```
          Phase 1    Phase 2    Phase 3    Phase 4    Phase 5
R1          ✓          ✓ (mitigated — OQ-1 resolved)
R2                     ██ (aggregation replaces direct-write)
R3                     ██
R4          ✓          ✓          ✓ (mitigated — OQ-2 resolved)
R5          ✓          ✓          ✓          ✓ (mitigated — OQ-4 resolved)
R6                                ██
R7          ██         ██         ██         ██
R8          ██
R9                                           ██
R10                               ██
R11                    ██         ██
R12         ██
R13                    ✓ (mitigated — label_hash)
R14                                         — (eliminated — Option 1)
R15                                         ██ (Option 1 distribution JOINs)
R16                    ██ (GROUP BY granularity)
R17                    ██         ██ (markup ORM)
R18                                         ██ (distribution regression)
R19                                         ✓ (resolved — aggregation sums both columns)
R20                    ✓ (mitigated — orchestration reorder)
R21                    ✓          ✓ (mitigated — VM split + orchestration reorder)
```

---

## R20 — Aggregation DELETE Scope Too Broad for Phase 2 Partial Deployment

**Status**: **MITIGATED** (Phase 2) — Option D adopted

### Problem

`aggregate_rates_to_daily_summary.sql` executes a DELETE that removes
all daily summary rows matching
`cost_model_rate_type IN ('Infrastructure', 'Supplementary') AND monthly_cost_type IS NULL`.
The subsequent INSERT only re-creates rows from `rates_to_usage` for
`metric_type IN ('cpu', 'memory', 'storage')`.

During the Phase 2 → Phase 3 gap, non-usage cost paths (VM costs,
tag costs) are still written directly to the daily summary by legacy
SQL files. These direct-written rows match the DELETE scope. If
aggregation ran **after** the legacy paths, it would delete their rows
without re-creating them — causing silent data loss.

### Decision: Option D — Reorder orchestration

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | **Narrow the DELETE scope** | Minimal change. | Requires `metric_type` column on daily summary (schema change). | **Rejected** |
| B | **Pull forward VM/tag costs into RTU in Phase 2** | Eliminates the gap entirely. | Increases Phase 2 scope significantly. | **Rejected** |
| C | **Defer aggregation to Phase 3** | Zero risk. | Creates a dual-path (RTU + legacy direct-write) — rejected by TL in [PR #5948](https://github.com/project-koku/koku/pull/5948). | **Rejected** |
| D | **Aggregation runs before legacy direct-write paths** | No schema change. No scope increase. No dual-path. Legacy paths write after the DELETE and are unaffected. | Orchestration ordering is a constraint. | **Selected** |

### Why Option D

1. **TL rejected dual-path architectures** — In [PR #5948 review](https://github.com/project-koku/koku/pull/5948),
   @myersCody wrote: _"My concern with removing the aggregation step is
   that we will be creating a dual path approach"_ — listing maintenance
   burden, silent divergence, and testing complexity as reasons. Option C
   would reintroduce exactly these problems.

2. **TL accepts orchestration ordering as an architectural pattern** — In
   the same review, @myersCody wrote: _"sequencing has always been
   important even with the current implementation. We can't distribute
   gpu costs without monthly_cost_gpu.sql running first."_ This confirms
   that call ordering is an expected and accepted constraint.

3. **No schema change required** — Option A would require adding a
   `metric_type` column to the daily summary table. Option D avoids
   this entirely.

4. **Phase 2 scope preserved** — Option B would pull VM, monthly, and
   tag cost migration forward from Phase 3, contradicting the phased
   delivery plan. Option D keeps Phase 2 focused on usage costs.

### Implementation

In `masu/processor/ocp/ocp_cost_model_cost_updater.py` →
`update_summary_cost_model_costs()`, the aggregation call was moved to
run immediately after the RTU INSERT, before the legacy direct-write
paths:

```
Phase 2 orchestration order (after fix):
  1. _update_usage_rates_to_usage()        ← RTU INSERT (usage costs)
  2. _update_per_rate_distributed_cost()   ← Phase 4 distribution on RTU
  3. _aggregate_rates_to_daily_summary()   ← DELETE+INSERT (only usage in RTU)
  4. _update_vm_usage_costs()              ← Legacy VM direct-write (survives)
  5. _update_markup_cost()                 ← Markup ORM UPDATE
  6. _update_monthly_cost()                ← Monthly costs (monthly_cost_type set, not affected by DELETE)
  7. Tag cost methods                      ← Legacy tag direct-write (survives)
  8. distribute_costs_and_update_ui_summary()
```

The aggregation DELETE (step 3) only removes stale cost-model rows
from the **previous** processing cycle. Legacy VM (step 4) and tag
(step 7) paths write their rows **after** the DELETE, so they are
never affected.

### Transitional → end-state

When Phase 3 migrates VM, monthly, and tag costs into RTU, steps 4–7
will be replaced by additional RTU INSERTs (before step 3). The
aggregation then naturally picks up all cost types from RTU with no
further reordering needed — converging to the target order documented
in `sql-pipeline.md § Insertion Point in Orchestration Code`.

---

## R21 — Transitional VM Cost Handling During Phase 2 → Phase 3 Gap

**Status**: **MITIGATED** (Phase 2-3) — resolved by R20 Option D

### Problem

On `main`, `_update_usage_costs()` handled both usage costs
(`populate_usage_costs()`) and VM costs (`populate_vm_usage_costs()`)
in a single method. Phase 2 replaces usage costs with the RTU pipeline
but VM costs are assigned to Phase 3 (`sql-pipeline.md` step 4a). The
design did not specify the transitional handling.

### Resolution

Phase 2 already correctly split `_update_usage_costs()` into two
independent paths:

1. **RTU pipeline** (`_update_usage_rates_to_usage()`) — replaces
   `populate_usage_costs()` for cpu/memory/storage. New Phase 2 code.
2. **`_update_vm_usage_costs()`** — keeps `populate_vm_usage_costs()`
   as a standalone method. Runs after aggregation per R20 Option D.

**Code reference** — On `main` (before Phase 2), `_update_usage_costs()`
contained both calls sequentially:
```python
# main branch: masu/processor/ocp/ocp_cost_model_cost_updater.py, _update_usage_costs()
report_accessor.populate_usage_costs(...)    # cpu/memory/storage
report_accessor.populate_vm_usage_costs(...) # VM costs
```

Phase 2 removes `_update_usage_costs()` entirely and replaces it with:
- `_update_usage_rates_to_usage()` + `_aggregate_rates_to_daily_summary()`
  for cpu/memory/storage (via RTU)
- `_update_vm_usage_costs()` for VM costs (legacy direct-write, survives
  the aggregation DELETE because it runs after it per R20 Option D)

Phase 3 will migrate `_update_vm_usage_costs()` to write to RTU
(step 4a in `sql-pipeline.md`), at which point the method is removed
and the aggregation picks up VM costs from RTU naturally.

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial: extracted from phased-delivery.md, data-model.md, sql-pipeline.md. Full risk register (R1-R19), decision rationales (R2/R3, R6, R11, R13, R17), Phase 2 benchmarks, R18 regression test approach, R19 aggregation question. |
| v1.1 | 2026-03-23 | **R19 RESOLVED (Option A)**: aggregation sums both `calculated_cost` and `distributed_cost`. R18: acceptance criteria confirmed — existing integration tests sufficient per tech lead. |
| v1.2 | 2026-04-16 | **R20 NEW → MITIGATED (Option D)**: Aggregation DELETE scope too broad for Phase 2 partial deployment. Fixed by reordering orchestration so aggregation runs before legacy VM/tag direct-write paths. Justified by TL's rejection of dual-path architectures ([PR #5948](https://github.com/project-koku/koku/pull/5948)) and acceptance of orchestration ordering as a constraint. **R21 NEW → MITIGATED**: Transitional VM cost handling resolved by the existing `_update_usage_costs()` → `_update_vm_usage_costs()` split plus R20 Option D ordering. |
