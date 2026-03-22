# Risk Register

Single source of truth for risks related to the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)).

---

## Risk Summary

| ID | Risk | Status | Phase | Mitigation |
|----|------|--------|-------|------------|
| **R1** | Celery task failure on month-end leaves no snapshot | Mitigated | 1 | Daily rolling `update_or_create`; last successful rate persists |
| **R2** | Large number of currency pairs × tenants increases task runtime | Open | 1 | Monitor task duration; batch operations if needed |
| **R3** | Overlapping static rates bypass serializer validation | Mitigated | 1 | DB-level `unique_together` on snapshot; serializer checks on `StaticExchangeRate` |
| **R4** | Pre-deployment months have no snapshot data | Accepted | 1 | Fallback to `ExchangeRateDictionary` (current behavior unchanged) |
| **R5** | Query handler `Case`/`When` with many months/currencies may be slow | Open | 1 | Benchmark with realistic currency pair counts |
| **R6** | Static rate deletion leaves gap before dynamic rate fills in | Low | 1 | Next daily task run populates dynamic rate; gap is at most 24 hours |

---

## R1 — Celery Task Month-End Failure

**Decision**: Mitigated via daily rolling snapshots.

The snapshot for the current month is updated every day, not just on the last
day. If the task fails on the last day of the month, the snapshot retains the
rate from the most recent successful run.

| # | Approach | Status |
|---|----------|--------|
| 1 | Snapshot only on last day of month | **Rejected** — single point of failure at month boundary |
| 2 | **Daily rolling `update_or_create`** | **Selected** — resilient to task failures; rate from most recent successful day persists |

**Linked from**: [pipeline-changes.md § Writer 1](./pipeline-changes.md#modified-get_daily_currency_rates--writer-1)

---

## R2 — Task Runtime with Many Tenants/Pairs

**Status**: Open. Requires monitoring after deployment.

**Context**: The daily task iterates over all tenants and all currency pairs.
With `T` tenants and `P` pairs, this is `O(T × P)` database operations per run.

For a deployment with 100 tenants and 170 currency pairs (current `VALID_CURRENCIES`
list), this is ~17,000 `update_or_create` calls. Each call involves a
`SELECT` + conditional `INSERT`/`UPDATE`, so ~34,000 queries per task run.

**Mitigation options** (apply if monitoring shows unacceptable runtime):

| # | Approach | Trade-off |
|---|----------|-----------|
| 1 | Batch `update_or_create` with raw SQL | More complex, but O(T) queries instead of O(T×P) |
| 2 | `bulk_create` with `update_conflicts=True` (Django 4.1+) | Cleaner API, requires Django version check |
| 3 | Parallelize per-tenant via Celery subtasks | Increases task complexity, but leverages worker pool |

**Linked from**: [pipeline-changes.md § Writer 1](./pipeline-changes.md#modified-get_daily_currency_rates--writer-1)

---

## R3 — Overlapping Static Rates

**Decision**: Mitigated at two levels.

- **Level 1 — Serializer**: The `StaticExchangeRateSerializer` validates that no
  overlapping validity periods exist for the same directional `(base_currency,
  target_currency)` pair before creating/updating a `StaticExchangeRate`.
  Returns HTTP 400 if overlap detected.

- **Level 2 — Snapshot table**: The `unique_together` constraint on
  `(year_month, base_currency, target_currency)` in `MonthlyExchangeRateSnapshot`
  prevents duplicate rows at the database level, regardless of which writer
  created them.

**Linked from**: [data-model.md § StaticExchangeRate](./data-model.md#staticexchangerate),
[data-model.md § MonthlyExchangeRateSnapshot](./data-model.md#monthlyexchangeratesnapshot)

---

## R4 — Pre-Deployment Month Gap

**Decision**: Accepted. Forward-only design.

Months before deployment have no snapshot rows in `MonthlyExchangeRateSnapshot`.
The query handler falls back to `ExchangeRateDictionary` for these months,
preserving current behavior exactly. Users see no change for historical data
that predates the feature deployment.

**Rejected alternative**: Backfilling historical months from
`ExchangeRateDictionary` at deployment time. This was rejected because:

1. `ExchangeRateDictionary` only stores the *latest* rates, not historical ones
2. Backfilling would create misleading "locked" rates that were never actually
   the rate for that month
3. The fallback path preserves the exact pre-deployment behavior

**Linked from**: [pipeline-changes.md § Reader](./pipeline-changes.md#modified-query-handler--reader)

---

## R5 — Query Handler Performance

**Status**: Open. Requires benchmarking.

**Context**: The `Case`/`When` annotation grows with
`months × unique_base_currencies` in the query range.

| Query Range | Base Currencies | `When` Clauses |
|-------------|----------------|----------------|
| 1 month | 1 | 1 |
| 3 months | 3 | 9 |
| 12 months | 5 | 60 |
| 12 months | 10 | 120 |

Django translates `Case`/`When` into SQL `CASE WHEN ... END` expressions.
PostgreSQL handles these efficiently for small-to-medium clause counts, but
performance should be validated with realistic data.

**Mitigation** (apply if benchmarking shows issues):

| # | Approach | Trade-off |
|---|----------|-----------|
| 1 | Cache resolved rates per request in `effective_exchange_rates` | Already implemented via `@cached_property` |
| 2 | Pre-compute exchange rate multiplier into a temp table or CTE | More complex SQL, but avoids large `CASE` expressions |
| 3 | Limit query range to 12 months maximum | Business constraint, may not be acceptable |

**Linked from**: [pipeline-changes.md § Reader](./pipeline-changes.md#modified-query-handler--reader)

---

## R6 — Static Rate Deletion Gap

**Decision**: Low risk, acceptable.

When a static rate is deleted, the `rate_type="static"` rows are removed from
`MonthlyExchangeRateSnapshot`. Until the next daily Celery task run (within 24
hours), queries for the affected month/pair will fall through to the `Case`/`When`
default value of `1` (no conversion).

**Impact**: A report queried during this gap window may show unconverted amounts
for the affected currency pair for the current month only. Past months are
unaffected (their dynamic rows were already finalized).

**Mitigation**: The serializer could proactively populate `rate_type="dynamic"`
rows from `ExchangeRateDictionary` when deleting a static rate, eliminating the
gap entirely. This is a Phase 1 enhancement if the gap proves problematic in
practice.

**Linked from**: [pipeline-changes.md § Writer 2](./pipeline-changes.md#static-rate--snapshot--writer-2)

---

## Risk × Phase Matrix

```
         Phase 1    Phase 2
R1       ✓
R2       ✓
R3       ✓
R4       ✓
R5       ✓          ✓ (if query range expands)
R6       ✓
```

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial risk register |
