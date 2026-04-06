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
| R7 | Dual-write divergence (JSON ↔ PriceList.rates ↔ Rate table) | Active | 1-4 | COST-575 already dual-writes JSON ↔ PriceList.rates. Phase 1 extends with delete-all + recreate Rate rows on every write. Three-way sync wrapped in `@transaction.atomic`. |
| R8 | `custom_name` migration produces ugly names | Active | 1 | Acceptable per PRD; users can rename. |
| R9 | Frontend tab restructure breaks workflows | Active | 4 | Usage cards move to adjacent tab, not removed. |
| R10 | Trino SQL dialect issues | Active | 3 | Test with Trino locally. |
| R11 | Concurrent cost model updates create duplicate rows | Active | 2-3 | Redis lock + DELETE-before-INSERT. |
| R12 | `CostModelManager.update()` missing `@transaction.atomic` | **MITIGATED** | 1 | COST-575 PR [#5963](https://github.com/project-koku/koku/pull/5963) already added `@transaction.atomic` to `update()`. |
| R13 | JSONB JOIN performance in aggregation | **MITIGATED** | 2 | `label_hash` column replaces JSONB GROUP BY. |
| R14 | Back-allocation rounding | **N/A** | — | Eliminated by IQ-9 Option 1. |
| R15 | Back-allocation JOIN complexity | **REPLACED** | 4 | Replaced by simpler RTU × daily summary JOIN. |
| R16 | Aggregation GROUP BY granularity mismatch | Active | 2 | `resource_id` confirmed absent from GROUP BY. |
| R17 | Markup ORM overhead | **MITIGATED** | 2 | ORM-first + SQL fallback if >30s. |
| R18 | Distribution SQL rewrite regression | Active | 4 | Old files preserved for rollback; new integration tests execute actual SQL and assert per-rate correctness (Phase 4 artifact). |
| R19 | Aggregation handling of `distributed_cost` | **RESOLVED** | 4 | Aggregation sums both `calculated_cost` and `distributed_cost` (Option A). |
| R20 | Concurrent API writes during migration corrupt data | **MITIGATED** | 1, 5 | Unleash write-freeze flag blocks cost model API writes during M2 and M5. |

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
regressions at the aggregate level. However, those tests mock
`_execute_raw_sql_query` and verify orchestration (method was called),
not mathematical correctness. Phase 4 adds **new integration tests**
that execute the actual distribution SQL against the test database and
assert per-rate proportional correctness, sum consistency, and edge
cases. See [phased-delivery.md § Concern 1 Resolution](./phased-delivery.md#concern-1-resolution--distribution-integration-tests).

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | Aggregate `distributed_cost` per (namespace, day, type) | Old vs new diff = 0 within NUMERIC(33,15) precision |
| 2 | Per-rate distributed rows sum to namespace total | SUM(per-rate) = aggregated `distributed_cost` per namespace |
| 3 | No orphaned distributed rows | Every distributed row traces back to a valid `RatesToUsage` source row |
| 4 | Zero-cost namespaces | Namespaces with `calculated_cost = 0` produce zero distributed rows (no divide-by-zero) |
| 5 | Single-node clusters | Distribution degenerates correctly (100% to the single node) |
| 6 | GPU distribution | GPU rates distribute by GPU-specific metrics, not CPU/memory |
| 7 | Execution time | New per-rate distribution ≤ 2× old distribution time per (source, date range) |
| 8 | **Independent cross-check** | Per-rate distributed amounts match Option 2's formula: `(rate_cost / total_cost) × aggregate_distributed_cost` within NUMERIC precision |
| 9 | Cost conservation | Net SUM(distributed_cost) across source + recipient rows = 0 per (day, distribution_type) |
| 10 | Idempotency | Distribution run twice produces identical RatesToUsage state |

Criteria 8-10 were added to compensate for removing IQ-9 Option 2 as a
runtime fallback. Criterion 8 is the most critical — it encodes Option
2's back-allocation math as a test assertion, providing the mathematical
cross-check that Option 2 would have provided in production.

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

## R20 — Migration Write-Corruption

**Status**: **MITIGATED** — Unleash write-freeze flag

### Problem

M2 (data migration) iterates `PriceListCostModelMap` rows, creates
`Rate` rows from `PriceList.rates` JSON, and injects `custom_name` back
into both `CostModel.rates` and `PriceList.rates` JSON blobs. Unlike
COST-575's migration `0011` (which uses `SELECT ... FOR UPDATE` per
row), M2 processes multiple price lists sequentially without row-level
locking across the full migration window.

If a user concurrently updates a cost model via the API during M2:

1. The API write could overwrite `custom_name` that M2 just injected
2. A new rate added via API would not have a corresponding `Rate` row
3. A rate deleted via API would leave orphaned `Rate` rows

The same concern applies to M5 (dropping JSON columns) — any in-flight
API write during column drop could fail with a database error.

### Decision: Unleash write-freeze flag

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | Row-level `SELECT FOR UPDATE` in M2 | No external dependency | Does not prevent new cost models created during migration; complex locking across multiple tables | **Rejected** |
| B | **Unleash write-freeze flag** | Simple, operator-controlled, follows existing koku patterns | Requires Unleash access; brief API downtime for cost model writes | **Selected** |
| C | Maintenance window (manual) | No code changes | Error-prone; no enforcement mechanism | **Rejected** |

### Implementation

- **Flag**: `cost-management.backend.disable-cost-model-writes`
- **Helper**: `is_cost_model_writes_disabled(schema)` in
  `masu/processor/__init__.py` (follows existing pattern)
- **Gating**: `CostModelSerializer.create()` and `update()` check the
  flag via `self.customer.schema_name`; raise `ValidationError` → HTTP 503
  with `Retry-After`
- **On-prem**: `MockUnleashClient` returns `False` by default; on-prem
  manages migration windows through operator coordination
- **Windows**: Enable before M2 / M5; disable after completion +
  validation

See [api-and-frontend.md § Migration Write-Freeze Flag](./api-and-frontend.md#migration-write-freeze-flag-unleash)
for full implementation details.

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
R12         ✓ (mitigated — COST-575 added @transaction.atomic)
R13                    ✓ (mitigated — label_hash)
R14                                         — (eliminated — Option 1)
R15                                         ██ (Option 1 distribution JOINs)
R16                    ██ (GROUP BY granularity)
R17                    ██         ██ (markup ORM)
R18                                         ██ (distribution regression)
R19                                         ✓ (resolved — aggregation sums both columns)
R20         ✓ (mitigated — Unleash write-freeze)                       ✓ (mitigated)
```

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial: extracted from phased-delivery.md, data-model.md, sql-pipeline.md. Full risk register (R1-R19), decision rationales (R2/R3, R6, R11, R13, R17), Phase 2 benchmarks, R18 regression test approach, R19 aggregation question. |
| v1.1 | 2026-03-23 | **R19 RESOLVED (Option A)**: aggregation sums both `calculated_cost` and `distributed_cost`. R18: acceptance criteria confirmed — existing integration tests sufficient per tech lead. |
| v1.2 | 2026-04-02 | **Align with COST-575.** R7: updated to reflect three-way sync (JSON + PriceList.rates + Rate table). R12: **MITIGATED** — `@transaction.atomic` already added to `update()` by COST-575 PR #5963. |
| v1.3 | 2026-04-02 | **R20: Migration write-corruption.** Add risk for concurrent API writes during M2/M5 migration windows. Mitigation: Unleash write-freeze flag (`cost-management.backend.disable-cost-model-writes`). Decision rationale (3 options evaluated). Update Risk × Phase Matrix. |
| v1.4 | 2026-04-02 | **Critical review.** Fix R20 gating location: `CostModelSerializer` (not `CostModelManager`) — serializer has `self.customer.schema_name`, manager does not. |
| v1.5 | 2026-04-02 | **Self-resolve Concern 1.** Strengthen R18 mitigation: add integration tests that execute actual distribution SQL (not mocked) as Phase 4 artifact. |
| v1.6 | 2026-04-03 | **R18 criteria expanded.** Add criteria 8 (independent cross-check via Option 2's formula), 9 (cost conservation), 10 (idempotency) to compensate for removing IQ-9 Option 2 as runtime fallback. |
