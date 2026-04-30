# Risk Register

Single source of truth for risks related to the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)).

---

## Risk Summary

| ID | Risk | Status | Phase | Mitigation |
|----|------|--------|-------|------------|
| **R1** | Celery task failure on month-end leaves no rate row | Mitigated | 1 | Daily rolling `update_or_create`; last successful rate persists |
| **R2** | Large number of currency pairs × tenants increases task runtime | Open | 1 | Monitor task duration; batch operations if needed |
| **R3** | Overlapping static rates bypass serializer validation | Mitigated | 1 | DB-level `unique_together` on `MonthlyExchangeRate`; serializer checks on `StaticExchangeRate` |
| **R4** | Pre-deployment months have no `MonthlyExchangeRate` data | Resolved | 1 | M2 migration seeds current month; pre-deployment months fall back to earliest available rate |
| **R5** | Query handler subquery performance with many months/currencies | Mitigated | 1 | `Subquery` approach uses indexed lookups instead of growing `CASE` expressions |
| **R6** | Static rate deletion leaves gap before dynamic rate fills in | Mitigated | 1 | Serializer proactively populates dynamic rows on static rate deletion; no gap |
| **R7** | User selects a target currency with no conversion path from bill currency | Mitigated | 1 | Show actionable error; currencies remain visible in dropdown |
| **R8** | No rates configured (static or dynamic) for a currency pair | Accepted | 1 | If `MonthlyExchangeRate` is empty: feature inactive, costs as-is. If rows exist but not for target: error. |

---

## R1 — Celery Task Month-End Failure

**Decision**: Mitigated via daily rolling updates.

The current month's row in `MonthlyExchangeRate` is updated every day, not just
on the last day. If the task fails on the last day of the month, the table
retains the rate from the most recent successful run.

| # | Approach | Status |
|---|----------|--------|
| 1 | Write only on last day of month | **Rejected** — single point of failure at month boundary |
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

- **Level 2 — `MonthlyExchangeRate` table**: The `unique_together` constraint on
  `(effective_date, base_currency, target_currency)` in `MonthlyExchangeRate`
  prevents duplicate rows at the database level, regardless of which writer
  created them.

**Linked from**: [data-model.md § StaticExchangeRate](./data-model.md#staticexchangerate),
[data-model.md § MonthlyExchangeRate](./data-model.md#monthlyexchangerate)

---

## R4 — Pre-Deployment Month Gap

**Decision**: Resolved. M2 migration seeds current month; pre-deployment months
fall back to earliest available rate.

The M2 migration seeds `MonthlyExchangeRate` with current-month data from
`ExchangeRateDictionary` at deployment time (see
[data-model.md § M2](./data-model.md#m2-create-and-seed-monthly_exchange_rate-table)).
This ensures the query handler has data from the moment of deployment. Months
before deployment have no rows for the exact month; the query handler falls back
to the **earliest available rate** for that currency pair (typically the
deployment month's rate). This provides the best available approximation rather
than showing unconverted costs. See
[pipeline-changes.md § Pre-Deployment Months](./pipeline-changes.md#pre-deployment-months).

**Why not seed historical months?** `ExchangeRateDictionary` only stores the
*latest* rates, not historical ones. Backfilling would create misleading rates
that were never actually the rate for those months. Seeding only the current
month avoids fabricating historical data.

**Linked from**: [pipeline-changes.md § Pre-Deployment Months](./pipeline-changes.md#pre-deployment-months)

---

## R5 — Query Handler Performance

**Decision**: Mitigated by adopting `Subquery` over `Case`/`When`.

**Context**: The original design used `Case`/`When` annotations that grew with
`months × unique_base_currencies` in the query range (e.g., 120 `WHEN` clauses
for a 12-month, 10-currency query). This was replaced with a correlated
`Subquery` that performs an indexed lookup on `MonthlyExchangeRate` per row.

The `Subquery` approach leverages the `unique_together` index on
`(effective_date, base_currency, target_currency)`, keeping lookup cost
constant regardless of the number of months or currencies in the query range.

**Residual risk**: Correlated subqueries add one additional indexed lookup per
row in the result set. For very large result sets, this could be slower than
a single `CASE` expression evaluated inline. Monitor query execution times
after deployment; if needed, PostgreSQL `LATERAL JOIN` or a CTE-based approach
can replace the `Subquery`.

**Linked from**: [pipeline-changes.md § Reader](./pipeline-changes.md#modified-query-handler--reader)

---

## R6 — Static Rate Deletion Gap

**Decision**: Mitigated via proactive dynamic rate population on delete.

When a static rate is deleted, the serializer removes `rate_type="static"` rows
from `MonthlyExchangeRate` and proactively populates `rate_type="dynamic"` rows
from the current `ExchangeRateDictionary` for the affected pairs/months. This
eliminates the data gap that would otherwise exist until the next daily Celery
task run.

**Linked from**: [pipeline-changes.md § Writer 2](./pipeline-changes.md#static-rate--monthlyexchangerate-upsert--writer-2)

---

## R7 — No Exchange Rate for Selected Currency

**Decision**: Mitigated via actionable error message.

**Context**: A currency may be available in the target currency dropdown (because
it appears in a static exchange rate pair or is an enabled dynamic currency) but
have no exchange rate path from the bill's source currency. For example:

- Cloud bill in `USD`
- Static rates define `EUR↔CHF` and `CNY↔SAR` (but not `USD↔EUR`)
- User selects `EUR` as target currency
- No `USD→EUR` rate exists (static or dynamic)

| # | Approach | Status |
|---|----------|--------|
| 1 | Filter dropdown to only show currencies with available conversion paths | **Rejected** — hides useful information from users; they can't see what currencies exist or what to ask their administrator to configure |
| 2 | **Show all available currencies; return actionable error when no conversion path exists** | **Selected** — transparent, informative, tells user exactly what to do |

**Error message**: *"No exchange rate available between {source} and {target}.
Ask your administrator to configure static exchange rates or enable dynamic
exchange rates."*

The error is returned as an HTTP 400 response. The report data is not returned
with unconverted or zero amounts.

**Linked from**: [api-and-frontend.md § Corner Case: No Exchange Rate](./api-and-frontend.md#corner-case-no-exchange-rate),
[pipeline-changes.md § Available Currency Resolution](./pipeline-changes.md#new-available-currency-resolution)

---

## R8 — No Rates Configured

**Decision**: Accepted. Graceful degradation.

**Context**: When no exchange rate data is available for a given currency pair:

- No static exchange rate has been defined for the pair
- No dynamic exchange rate exists for the pair (either `CURRENCY_URL` was never
  configured, the API never returned that pair, or no rates have been fetched yet)

**Behavior**: Two distinct cases:

1. **`MonthlyExchangeRate` is completely empty** (feature not configured): The
   constant currency feature is inactive. No currencies are enabled, so the
   serializer rejects any explicit `currency` parameter. Without a `currency`
   parameter, the `Coalesce("exchange_rate", Value(1))` fallback in provider
   maps ensures all exchange rate annotations resolve to `1`, so costs are
   returned as-is in their original bill currency. This is the default state
   for fresh deployments without `CURRENCY_URL` or static rates.

2. **`MonthlyExchangeRate` has rows but none for the target currency**: The
   feature is active but the specific currency pair is missing. Rate resolution
   follows the priority:
   1. **Static rates** — used if defined for the pair
   2. **Dynamic rates** — used as fallback if no static rate exists
   3. **Error** — if neither exists, the API returns an actionable error:
      *"No exchange rate available. Ask your administrator to configure static
      exchange rates or enable dynamic exchange rates."*

If no currencies are visible at all (all disabled and no static rates), the
currency dropdown is either hidden or shows *"No exchange rates available"*.

**Recovery path**: The administrator can:

1. Define static exchange rates via the CRUD API (`/settings/currency/exchange_rate/`)
2. Configure `CURRENCY_URL` to fetch dynamic rates from an exchange rate API
3. Enable discovered currencies in Settings to make them visible in the dropdown

**Linked from**: [pipeline-changes.md § Writer 1](./pipeline-changes.md#modified-get_daily_currency_rates--writer-1),
[data-model.md § EnabledCurrency](./data-model.md#enabledcurrency)

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
R7       ✓
R8       ✓
```

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial risk register |
| v1.1 | 2026-03-24 | Added R7 (no-rate corner case) and R8 (no rates configured) |
| v1.2 | 2026-03-24 | Reframed R8: removed airgapped mode concept. Rate resolution: static first, dynamic fallback, error if neither. |
| v1.3 | 2026-03-29 | R6: upgraded from Low to Mitigated — serializer proactively populates dynamic rows on delete (aligns with pipeline-changes.md and api-and-frontend.md) |
| v1.4 | 2026-03-30 | Renamed `MonthlyExchangeRateSnapshot` → `MonthlyExchangeRate` throughout. Updated R3, R4, R6 references. |
| v1.5 | 2026-03-30 | R4 resolved: M2 seeds current-month data, eliminating need for `ExchangeRateDictionary` fallback. |
| v1.6 | 2026-04-12 | R5 mitigated: `Subquery` approach replaces `Case`/`When`, eliminating O(months × currencies) scaling concern. |
| v1.7 | 2026-04-13 | R4: updated to reflect earliest-available-rate fallback for pre-deployment months (aligns with pipeline-changes.md v2.1). |
| v1.8 | 2026-04-28 | R8: updated CRUD API URL to `settings/currency/exchange_rate/`. |
| v1.9 | 2026-04-28 | R8: added "costs as-is" behavior — when `MonthlyExchangeRate` is empty, feature is inactive, validation skipped, costs returned in original currency. |
| v2.0 | 2026-04-30 | R8: clarified "costs as-is" — serializer blocks non-enabled currencies; query handler skip is secondary defense. |
