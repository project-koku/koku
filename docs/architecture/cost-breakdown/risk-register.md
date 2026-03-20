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
| R18 | Distribution SQL rewrite regression | Active | 4 | Old files preserved for rollback; regression tests. |
| R19 | Aggregation handling of `distributed_cost` | **Open** | 4 | [Details](#r19-aggregation-handling-of-distributed_cost) |

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

**Status**: Active (Phase 4)

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

### Orchestration phasing note

The target orchestration order (distribution before aggregation) applies
from **Phase 4 onward**. During Phases 2-3, the legacy ordering is
preserved: `RatesToUsage INSERT → aggregate → distribute (on daily
summary) → UI summary`. Phase 4 rewires to: `RatesToUsage INSERT →
raw cost → distribute (on RatesToUsage) → aggregate → UI summary`.

---

## R19 — Aggregation Handling of `distributed_cost`

**Status**: Open — requires tech lead input

### Problem

With IQ-9 Option 1, distribution writes per-rate distributed rows
back to `RatesToUsage` with a `distributed_cost` column. The
aggregation SQL (`aggregate_rates_to_daily_summary.sql`) currently
only sums `calculated_cost` by `metric_type` into
`cost_model_cpu_cost / memory_cost / volume_cost` on the daily summary.

The daily summary also needs `distributed_cost` populated for:
- UI summary tables (`reporting_ocp_cost_summary_*_p`)
- Sankey chart (via report API)

### Options

| # | Approach | Pros | Cons |
|---|----------|------|------|
| A | **Aggregation sums both** — extend aggregation SQL to also SUM `distributed_cost` from `RatesToUsage` into the daily summary | Single write path. Consistent with single-source-of-truth. | Aggregation SQL becomes more complex (two types of rows: rate calculations and distributed). |
| B | **Distribution dual-writes** — new distribution SQL writes per-rate rows to `RatesToUsage` AND aggregated `distributed_cost` to daily summary | Aggregation SQL stays unchanged. Daily summary gets same format as today. | Distribution has two write targets; slight dual-path concern. |

**Recommendation**: Option B is lower risk. The new distribution SQL
already JOINs the daily summary for usage metrics — writing the
aggregated `distributed_cost` back to the daily summary in the same
SQL is a trivial addition. This means:
- `RatesToUsage` gets per-rate distributed rows (for breakdown tree)
- Daily summary gets aggregated `distributed_cost` (for existing pipeline)
- Aggregation SQL stays unchanged (only handles `calculated_cost`)

**Decision needed from tech lead.**

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
R19                                         ██ (aggregation + distributed_cost)
```

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial: extracted from phased-delivery.md, data-model.md, sql-pipeline.md. Full risk register (R1-R19), decision rationales (R2/R3, R6, R11, R13, R17), Phase 2 benchmarks, R18 regression test approach, R19 aggregation question. |
