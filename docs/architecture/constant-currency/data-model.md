# Data Model Changes

Data model for the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)). Introduces three
new tenant-scoped models and their migrations.

> **See also**: [README.md § Architecture at a Glance](./README.md#architecture-at-a-glance)
> for the data flow diagrams that show how these models fit into the pipeline.

---

## Current State

**Public schema models** (no tenant context needed):

| Model | App | Purpose |
|-------|-----|---------|
| `ExchangeRates` | `api.currency` | One row per target currency. `currency_type` (CharField) stores the currency code (e.g., `"eur"`); `exchange_rate` (FloatField) stores the rate vs USD. Updated daily by `get_daily_currency_rates`. |
| `ExchangeRateDictionary` | `api.currency` | Single row: `currency_exchange_dictionary` JSONField — nested dict `{base: {target: rate}}`. Rebuilt daily by `build_exchange_dictionary()` in `api/currency/utils.py`. |

**Example `ExchangeRates` rows**:

| id | currency_type | exchange_rate |
|----|---------------|---------------|
| 1 | `eur` | `0.87` |
| 2 | `gbp` | `0.74` |
| 3 | `cny` | `7.23` |
| 4 | `jpy` | `149.50` |

All rates are relative to USD (the base currency used in `CURRENCY_URL`).

**Example `ExchangeRateDictionary` row** (single row in the table):

| id | currency_exchange_dictionary |
|----|------------------------------|
| 1 | *(see JSON below)* |

**Current exchange rate storage** (simplified):

```json
{
  "USD": {"EUR": 0.87, "GBP": 0.74, "CNY": 7.23, ...},
  "EUR": {"USD": 1.15, "GBP": 0.85, "CNY": 8.31, ...},
  ...
}
```

**Limitation**: No historical rate storage. Only the latest snapshot exists.
All months in a report query use the same rate, meaning historical reports
drift as rates change daily.

---

## New Models

All models are placed in `cost_models` app (tenant schema). See
[README.md § IQ-1](./README.md#iq-1-model-placement--resolved) for the
placement rationale.

### `StaticExchangeRate`

User-defined exchange rates with validity periods.

```python
class StaticExchangeRate(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
    base_currency = models.CharField(max_length=5)
    target_currency = models.CharField(max_length=5)
    exchange_rate = models.DecimalField(max_digits=33, decimal_places=15)
    start_date = models.DateField()   # first day of a natural month
    end_date = models.DateField()     # last day of a natural month (or later)
    version = models.IntegerField(default=1)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "static_exchange_rate"
        ordering = ["-updated_timestamp"]
```

**Example `static_exchange_rate` rows**:

| uuid | base_currency | target_currency | exchange_rate | start_date | end_date | version | created_timestamp | updated_timestamp |
|------|---------------|-----------------|---------------|------------|----------|---------|-------------------|-------------------|
| `a1b2c3d4-...` | `USD` | `EUR` | `0.920000000000000` | `2026-01-01` | `2026-03-31` | 1 | `2026-01-15 10:30:00+00` | `2026-01-15 10:30:00+00` |
| `e5f6a7b8-...` | `USD` | `GBP` | `0.780000000000000` | `2026-01-01` | `2026-01-31` | 2 | `2026-01-10 08:00:00+00` | `2026-01-20 14:22:00+00` |
| `c9d0e1f2-...` | `EUR` | `GBP` | `0.848000000000000` | `2026-02-01` | `2026-06-30` | 1 | `2026-02-01 09:00:00+00` | `2026-02-01 09:00:00+00` |

In this example:
- The `USD→EUR` rate of `0.92` applies for Jan–Mar 2026 (overrides dynamic rates for those months)
- The `USD→GBP` rate was updated once (`version=2`) and only covers January
- The `EUR→GBP` rate covers Feb–Jun 2026

**Constraints** (enforced in serializer validation):

- `base_currency` and `target_currency` must be in `VALID_CURRENCIES`
- `base_currency != target_currency`
- `start_date` must be the 1st of a month; `end_date` must be the last day of
  that same month or a later month
- No overlapping validity periods for the same `(base_currency, target_currency)`
  directional pair
- `version` auto-increments on update (managed by serializer, not DB trigger)

**Computed properties**:

- `name` (read-only): `"{base_currency}-{target_currency}"`

**Bidirectional behavior**: If `USD→EUR` is defined but `EUR→USD` is not, the
inverse (`1/rate`) is used automatically. If both directions are explicitly
defined, each uses its own rate.

**Registration points**: None. This model is accessed only via the CRUD API
(see [api-and-frontend.md](./api-and-frontend.md)) and has side effects on
`MonthlyExchangeRate` via the serializer.

### `EnabledCurrency`

Tracks which currencies are visible in the target currency dropdown. Currencies
must be explicitly enabled by an administrator before they appear in the
dropdown. All currencies are always stored in `MonthlyExchangeRate` regardless
of their enabled status — the `enabled` flag only controls dropdown visibility.

```python
class EnabledCurrency(models.Model):
    currency_code = models.CharField(max_length=5, unique=True)
    enabled = models.BooleanField(default=False)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "enabled_currency"
        ordering = ["currency_code"]
```

**Example `enabled_currency` rows**:

| id | currency_code | enabled | created_timestamp | updated_timestamp |
|----|---------------|---------|-------------------|-------------------|
| 1 | `USD` | `true` | `2026-01-01 06:00:00+00` | `2026-01-01 06:00:00+00` |
| 2 | `EUR` | `true` | `2026-01-01 06:00:00+00` | `2026-01-15 10:30:00+00` |
| 3 | `GBP` | `false` | `2026-01-01 06:00:00+00` | `2026-01-01 06:00:00+00` |
| 4 | `CNY` | `false` | `2026-01-01 06:00:00+00` | `2026-01-01 06:00:00+00` |
| 5 | `JPY` | `false` | `2026-01-01 06:00:00+00` | `2026-01-01 06:00:00+00` |

In this example, `USD` and `EUR` are enabled and will appear in the target
currency dropdown. `GBP`, `CNY`, and `JPY` were discovered by the daily Celery
task (fetched from the exchange rate API) but have not yet been enabled by an
administrator — they are stored in `MonthlyExchangeRate` but hidden from the
dropdown.

**Lifecycle**:

| Event | Action |
|-------|--------|
| Daily Celery task fetches from exchange rate API | Creates `EnabledCurrency` rows with `enabled=False` for any newly discovered currencies not already in the table |
| Administrator enables a currency in Settings | Sets `enabled=True` |
| Administrator disables a currency in Settings | Sets `enabled=False` |

**How currencies become "available" in dropdowns**:

A currency is visible in the target currency dropdown if **any** of the
following are true:

1. It has `enabled=True` in `EnabledCurrency`
2. It appears in any `StaticExchangeRate` pair (static rates make their currencies
   visible regardless of the `EnabledCurrency` status)

**Corner case — no usable rate**: A currency may be available in the dropdown but
have no exchange rate path from the bill's source currency. In this case, the API
returns an error: *"No exchange rate available. Ask your administrator to configure
static exchange rates or enable dynamic exchange rates."* See
[api-and-frontend.md § Corner Case: No Exchange Rate](./api-and-frontend.md#corner-case-no-exchange-rate).

**No `CURRENCY_URL` configured**: When the URL is not set, no dynamic currencies
are discovered by the Celery task, so no rows are created automatically. The
table may still contain previously fetched currencies or manually-created rows.
The system does not treat this as a special mode — it uses whatever rates are
available (static first, dynamic fallback, error if neither exists). If no
currencies are visible (all disabled and no static rates), the currency dropdown
is hidden or shows *"No exchange rates available."*

**Registration points**: None. Accessed via the Settings API (see
[api-and-frontend.md § Currency Enablement](./api-and-frontend.md#currency-enablement-settings-api)).

### `MonthlyExchangeRate`

**Single source of truth for exchange rates used in reports.** Stores both
static and dynamic rates as per-pair rows, one row per month. The query handler
reads from this table for **all months** — current and past alike. For the
current month, dynamic rows are updated daily by the Celery task; once the
month rolls over, rows are never updated again (automatic finalization).

```python
class RateType(models.TextChoices):
    STATIC = "static", "Static"
    DYNAMIC = "dynamic", "Dynamic"

class MonthlyExchangeRate(models.Model):
    effective_date = models.DateField()  # First day of month: 2026-03-01
    base_currency = models.CharField(max_length=5)
    target_currency = models.CharField(max_length=5)
    exchange_rate = models.DecimalField(max_digits=33, decimal_places=15)
    rate_type = models.CharField(max_length=10, choices=RateType.choices)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    updated_timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monthly_exchange_rate"
        unique_together = ("effective_date", "base_currency", "target_currency")
```

**Constraints**:

- `unique_together` ensures one rate per `(effective_date, base, target)` triple
- `effective_date` stores the first day of the month (`2026-03-01`), consistent
  with existing patterns like `usage_start` and `billing_period_start`
- `rate_type` is constrained to `RateType.choices` (`"static"` or `"dynamic"`)

**Example `monthly_exchange_rate` rows**:

| id | effective_date | base_currency | target_currency | exchange_rate | rate_type | created_timestamp | updated_timestamp |
|----|----------------|---------------|-----------------|---------------|-----------|-------------------|-------------------|
| 1 | `2026-01-01` | `USD` | `EUR` | `0.920000000000000` | `static` | `2026-01-15 10:30:00+00` | `2026-01-15 10:30:00+00` |
| 2 | `2026-02-01` | `USD` | `EUR` | `0.920000000000000` | `static` | `2026-01-15 10:30:00+00` | `2026-01-15 10:30:00+00` |
| 3 | `2026-03-01` | `USD` | `EUR` | `0.920000000000000` | `static` | `2026-01-15 10:30:00+00` | `2026-01-15 10:30:00+00` |
| 4 | `2026-01-01` | `USD` | `GBP` | `0.780000000000000` | `static` | `2026-01-10 08:00:00+00` | `2026-01-20 14:22:00+00` |
| 5 | `2026-02-01` | `USD` | `GBP` | `0.740000000000000` | `dynamic` | `2026-02-01 06:00:00+00` | `2026-02-01 06:00:00+00` |
| 6 | `2026-03-01` | `USD` | `GBP` | `0.738500000000000` | `dynamic` | `2026-03-01 06:00:00+00` | `2026-03-24 06:00:00+00` |
| 7 | `2026-01-01` | `USD` | `CNY` | `7.230000000000000` | `dynamic` | `2026-01-01 06:00:00+00` | `2026-01-31 06:00:00+00` |
| 8 | `2026-02-01` | `USD` | `CNY` | `7.185000000000000` | `dynamic` | `2026-02-01 06:00:00+00` | `2026-02-28 06:00:00+00` |
| 9 | `2026-03-01` | `USD` | `CNY` | `7.195000000000000` | `dynamic` | `2026-03-01 06:00:00+00` | `2026-03-30 06:00:00+00` |

In this example:
- **Rows 1–3**: `USD→EUR` uses a **static** rate (`0.92`) for all three months
  because the user defined a static rate covering Jan–Mar 2026. The daily Celery
  task skips this pair for those months.
- **Row 4**: `USD→GBP` uses a **static** rate (`0.78`) for January only (the
  static rate's `end_date` was `2026-01-31`).
- **Rows 5–6**: `USD→GBP` falls back to **dynamic** rates for Feb and Mar since
  no static rate covers those months. The dynamic rate is updated daily by the
  Celery task.
- **Rows 7–9**: `USD→CNY` has no static rate defined, so all months use
  **dynamic** rates. Row 9 is the **current month** — its `exchange_rate` is
  overwritten daily with the latest rate from the API. Once March ends, row 9
  is locked and never updated again.

**Two writers, one reader path**:

- **Writer 1** (Celery task): Upserts `rate_type=RateType.DYNAMIC` rows daily for
  the current month, skipping pairs with existing static rates. See
  [pipeline-changes.md § Writer 1](./pipeline-changes.md#modified-get_daily_currency_rates--writer-1).
- **Writer 2** (CRUD serializer): Upserts `rate_type=RateType.STATIC` rows for each
  month in a static rate's validity period. See
  [pipeline-changes.md § Writer 2](./pipeline-changes.md#static-rate--monthlyexchangerate-upsert--writer-2).
- **Reader** (query handler): Resolves per-month rates via correlated
  `Subquery` annotations on `MonthlyExchangeRate`. See
  [pipeline-changes.md § Rate Resolution](./pipeline-changes.md#rate-resolution-strategy).

**Registration points**: None. Not added to `UI_SUMMARY_TABLES` or any cleaner
registry — this is a configuration/metadata table, not a reporting table.

---

## Database Migration Plan

### Migration Sequence Overview

```mermaid
graph TD
    M1["M1: Create<br/>static_exchange_rate"] --> M2["M2: Create<br/>monthly_exchange_rate"]
```

All are standard `CreateModel` migrations in `cost_models/migrations/`. Since
`cost_models` is a tenant app, migrations run in each tenant schema via
`migrate_schemas`.

### M1: Create `static_exchange_rate` Table

| Field | Value |
|-------|-------|
| **Phase** | 1 |
| **Type** | `CreateModel` (standard, no partitioning) |
| **App** | `cost_models` |
| **Depends on** | Previous `cost_models` migration |
| **Rollback** | `DeleteModel` |

**What migration does NOT do**: No data migration needed. Table starts empty;
populated via user CRUD.

### M2: Create and seed `monthly_exchange_rate` Table

| Field | Value |
|-------|-------|
| **Phase** | 1 |
| **Type** | `CreateModel` + `RunPython` (seed current month) |
| **App** | `cost_models` |
| **Depends on** | M1 |
| **Rollback** | `DeleteModel` (seed data dropped with the table) |

**Seed step**: After creating the table, a `RunPython` step reads from
`ExchangeRateDictionary` (public schema) and populates `MonthlyExchangeRate`
with `rate_type=dynamic` rows for the **current month**. Since `cost_models`
is a tenant app, `migrate_schemas` already executes this migration once per
tenant with the correct schema context — no explicit tenant loop is needed.
`ExchangeRateDictionary` (a shared/public model) remains accessible because
`django-tenants` sets `search_path` to `<tenant_schema>, public`.

```python
def seed_current_month(apps, schema_editor):
    """Seed MonthlyExchangeRate with current-month rates from ExchangeRateDictionary."""
    ExchangeRateDictionary = apps.get_model("api", "ExchangeRateDictionary")
    MonthlyExchangeRate = apps.get_model("cost_models", "MonthlyExchangeRate")

    erd = ExchangeRateDictionary.objects.first()
    if not erd or not erd.currency_exchange_dictionary:
        return

    current_month = date.today().replace(day=1)

    rows = []
    for base_cur, targets in erd.currency_exchange_dictionary.items():
        for target_cur, rate in targets.items():
            if base_cur == target_cur:
                continue
            rows.append(MonthlyExchangeRate(
                effective_date=current_month,
                base_currency=base_cur,
                target_currency=target_cur,
                exchange_rate=rate,
                rate_type="dynamic",
            ))
    MonthlyExchangeRate.objects.bulk_create(rows, ignore_conflicts=True)
```

If `ExchangeRateDictionary` is empty (e.g., fresh deployment with no
`CURRENCY_URL` configured), the seed step is a no-op — there are no dynamic
rates to seed, and the table starts empty. The daily Celery task and static
rate CRUD will populate it going forward.

### M3: Create `enabled_currency` Table

| Field | Value |
|-------|-------|
| **Phase** | 1 |
| **Type** | `CreateModel` (standard, no partitioning) |
| **App** | `cost_models` |
| **Depends on** | Previous `cost_models` migration |
| **Rollback** | `DeleteModel` |

**What migration does NOT do**: No data migration needed. Table is populated
going forward by the daily Celery task (which creates rows with `enabled=False`
for newly discovered currencies) and by administrator actions in Settings.

### Phase-to-Migration Mapping

| Phase | Migrations | Description |
|-------|-----------|-------------|
| 1 | M1, M2, M3 | Create all new tables |
| 2 | TBD | Audit history tables (future) |

**Note**: No tables are partitioned (`set_pg_extended_mode` not needed).
`MonthlyExchangeRate` volume is bounded by `months × currency_pairs` — small
enough for a standard table.

### On-Prem Considerations

All models use standard Django ORM (no Trino, no raw SQL). Fully compatible
with on-prem (PostgreSQL-only) mode. No `trino_sql/` or `self_hosted_sql/`
changes required.

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial data model design |
| v1.1 | 2026-03-24 | Added `EnabledCurrency` model, M4 migration |
| v1.2 | 2026-03-24 | Simplified enablement: `enabled` flag only controls dropdown visibility, not snapshotting |
| v1.3 | 2026-03-24 | Removed airgapped mode concept. Rate resolution: static first, dynamic fallback, error if neither. |
| v1.4 | 2026-03-26 | Clarified `StaticExchangeRateDictionary` as source of truth for static rates; `MonthlyExchangeRateSnapshot` as historical rate storage for reports. |
| v1.5 | 2026-03-29 | Replaced `year_month` CharField with `effective_date` DateField on `MonthlyExchangeRateSnapshot` for consistency with existing date field patterns (`usage_start`, `billing_period_start`). |
| v1.6 | 2026-03-30 | Renamed `MonthlyExchangeRateSnapshot` → `MonthlyExchangeRate` and promoted it to single source of truth for all months (current and past). Removed `StaticExchangeRateDictionary` — no longer needed since query handlers read from `MonthlyExchangeRate` for all months. Renumbered migrations (M3 is now `enabled_currency`; old M3 removed). |
| v1.7 | 2026-03-30 | M2 now seeds current-month data from `ExchangeRateDictionary` during migration. Eliminates `ExchangeRateDictionary` fallback in query handler. |
| v1.8 | 2026-04-12 | Updated reader description to reflect `Subquery`-based rate resolution (replaces `Case`/`When`). |
| v1.9 | 2026-04-13 | Fixed `ExchangeRates` model description: actual fields are `currency_type` (CharField) and `exchange_rate` (FloatField), not `base_currency`/`exchange_rates` JSONField. Removed non-existent `updated_timestamp` column from `ExchangeRateDictionary` example. |
