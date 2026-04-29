# API and Frontend Changes

API and frontend modifications for the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)). Covers the new
CRUD endpoint for static exchange rates, report response enhancements, and
OpenAPI updates.

---

## Exchange Rate Endpoint

### URL

```
GET/POST        /api/cost-management/v1/settings/currency/exchange_rate/
PUT/DELETE      /api/cost-management/v1/settings/currency/exchange_rate/{uuid}/
POST/DELETE     /api/cost-management/v1/settings/currency/exchange_rate/{code}/enable/
```

### Registration

**File**: `koku/api/urls.py`

Registered as explicit `path()` entries mapping to `StaticExchangeRateViewSet`
and `EnabledCurrencyView`.

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `base_currency` | string | Filter by base currency code (e.g., `USD`) |
| `target_currency` | string | Filter by target currency code (e.g., `EUR`) |
| `start_date` | date | Filter rates active on or after this date |
| `end_date` | date | Filter rates active on or before this date |

### View

**File**: `koku/cost_models/static_exchange_rate_view.py`

The `StaticExchangeRateViewSet` handles CRUD for exchange rates. The `list`
action returns exchange rates grouped by target currency with enabled status
(via `CurrencyExchangeRateSerializer`). All other actions use the flat
`StaticExchangeRateSerializer`.

**Permission**: `CostModelsAccessPermission` — requires the **Price List
Administrator** role. Same permission used for cost model CRUD.

**File**: `koku/api/settings/currency_views.py`

The `EnabledCurrencyView` handles currency enablement via POST (enable) and
DELETE (disable). No request body required.

**Permission**: `SettingsAccessPermission` — requires the **Cost Management
Administrator** role.

### Serializer

**File**: New `koku/cost_models/static_exchange_rate_serializer.py`

**Validation rules**:

| Rule | Description |
|------|-------------|
| Currency codes | `base_currency` and `target_currency` must be in `VALID_CURRENCIES` |
| Different currencies | `base_currency != target_currency` |
| Month boundaries | `start_date` must be 1st of month; `end_date` must be last day of a month |
| No overlap | No overlapping validity periods for same directional `(base, target)` pair |
| Name | Read-only computed field: `"{base_currency}-{target_currency}"` |

**Side effects** (see [pipeline-changes.md § Writer 2](./pipeline-changes.md#static-rate--monthlyexchangerate-upsert--writer-2)):

All side effects are wrapped in a database transaction (`transaction.atomic()`)
together with the `StaticExchangeRate` write. If any side effect fails, the
`StaticExchangeRate` change is rolled back, preventing an inconsistent state.

- **On create/update**:
  1. Upserts `rate_type=RateType.STATIC` rows in `MonthlyExchangeRate`
     for each affected month (overwrites any existing dynamic row for the same
     pair/month via the `unique_together` constraint)
- **On delete**:
  1. Removes `rate_type=RateType.STATIC` rows for affected months, then
     proactively populates `rate_type=RateType.DYNAMIC` rows from the current
     `ExchangeRateDictionary` to avoid a data gap until the next daily Celery run

### Example: GET List Response

The list endpoint returns exchange rates grouped by target currency. Each
currency entry includes its enabled status and a nested list of exchange rates.
Only currencies with at least one `StaticExchangeRate` record appear.

```json
{
  "meta": { "count": 2 },
  "data": [
    {
      "code": "EUR",
      "name": "Euro",
      "symbol": "€",
      "enabled": true,
      "exchange_rates": [
        {
          "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "name": "USD-EUR",
          "base_currency": "USD",
          "target_currency": "EUR",
          "exchange_rate": "0.870000000000000",
          "start_date": "2026-01-01",
          "end_date": "2026-03-31",
          "created_timestamp": "2026-01-15T10:30:00Z",
          "updated_timestamp": "2026-01-15T10:30:00Z"
        }
      ]
    },
    {
      "code": "GBP",
      "name": "British Pound",
      "symbol": "£",
      "enabled": false,
      "exchange_rates": [
        {
          "uuid": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
          "name": "USD-GBP",
          "base_currency": "USD",
          "target_currency": "GBP",
          "exchange_rate": "0.740000000000000",
          "start_date": "2026-01-01",
          "end_date": "2026-06-30",
          "created_timestamp": "2026-01-15T10:30:00Z",
          "updated_timestamp": "2026-02-01T14:00:00Z"
        }
      ]
    }
  ]
}
```

### Example: Create Request

```json
{
  "base_currency": "USD",
  "target_currency": "EUR",
  "exchange_rate": "0.870000000000000",
  "start_date": "2026-04-01",
  "end_date": "2026-06-30"
}
```

### No Feature Flags

This endpoint is always available. No Unleash feature flag gating.

---

## Currency Enablement

Currency enablement is managed via the exchange rate endpoint. The enabled
status for each currency is visible in the GET list response and can be
toggled individually.

### URL

```
POST    /api/cost-management/v1/settings/currency/exchange_rate/{code}/enable/
DELETE  /api/cost-management/v1/settings/currency/exchange_rate/{code}/enable/
```

- **POST**: Enables the currency (creates an `EnabledCurrency` row). No request body.
- **DELETE**: Disables the currency (removes the `EnabledCurrency` row). No request body.

Both return `204 No Content`.

### View

**File**: `koku/api/settings/currency_views.py` — `EnabledCurrencyView`

**Permission**: `SettingsAccessPermission` — requires the **Cost Management
Administrator** role.

**Side effects**: Enabling or disabling a currency only affects its visibility
in the target currency dropdown. It does not affect the `MonthlyExchangeRate`,
`ExchangeRateDictionary`, `ExchangeRates`, or `StaticExchangeRate` tables.

### No `CURRENCY_URL` Configured

When no `CURRENCY_URL` is configured, no dynamic exchange rates are fetched by
the Celery task. The `EnabledCurrency` table only contains currencies that an
administrator has explicitly enabled. The full list of ISO 4217 currencies is
always available from Babel.

---

## Available Currencies for Dropdown

The target currency dropdown in the UI shows only currencies that an
administrator has explicitly enabled.

### Availability Rule

| Source | Rule | Example |
|--------|------|---------|
| **EnabledCurrency** | Currency exists in `EnabledCurrency` table | USD, EUR enabled → appear in dropdown |

Defining a static exchange rate does **not** automatically make its currencies
available in the report dropdown. The administrator must explicitly enable them.

The settings admin page (`GET settings/currency/exchange_rate/`) shows all
currencies with static rates regardless of enabled status, so the administrator
can see and manage exchange rates without needing to enable currencies first.

### No Currencies Available

When no currencies exist in `EnabledCurrency` (none enabled), the currency
dropdown should either be **hidden** or show a message:
*"No exchange rates available."* Whichever approach is simpler to implement.

---

## Corner Case: No Exchange Rate

A currency may appear in the dropdown (because it is enabled) but have **no
exchange rate path** from the bill's source currency to the selected target
currency.

**Example**:
- Cloud bill arrives in `USD`
- Static rates define `EUR↔CHF` and `CNY↔SAR`
- User wants to see costs in `EUR`
- There is no `USD→EUR` rate (static or dynamic)

### Behavior

There are two distinct cases:

**1. Feature not configured** (`MonthlyExchangeRate` is empty): When no exchange
rates have been configured at all (no `CURRENCY_URL`, no static rates, no Celery
task run), the constant currency feature is inactive. Validation is skipped and
costs are returned as-is in their original bill currency. The
`Coalesce("exchange_rate", Value(1))` fallback in provider maps ensures NULL
annotations resolve to `1` (no conversion). This is the default state for fresh
deployments.

**2. Feature active but target currency has no rates** (`MonthlyExchangeRate`
has rows but none for the target): The API returns an error:

```json
{
  "errors": [
    {
      "detail": "No exchange rate available for EUR. Ask your administrator to configure static exchange rates or enable dynamic exchange rates.",
      "status": 400,
      "source": "currency"
    }
  ]
}
```

The frontend should display this error message to the user. The report data is
**not** returned with unconverted amounts — the request fails with a clear,
actionable error.

**Make all available currencies visible** in the dropdown (`EUR`, `CHF`, `CNY`,
`SAR`).

**Rationale**: This approach was preferred over filtering the dropdown to only
show currencies with available conversion paths because:

1. It shows users what currencies exist in the system, even if they can't
   currently convert to them
2. The error message tells the user exactly what to do (configure rates or
   enable dynamic exchange)
3. It avoids confusing situations where a user expects to see a currency but
   it's silently hidden

---

## Report Response Enhancement

### Changed: Report `meta` Output

**File**: `koku/api/report/queries.py` — `_format_query_response` and
`_initialize_response_output`

Add `exchange_rates_applied` to the report response `meta`. This provides
transparency on which rates (static vs dynamic) were used and for which periods.

```json
{
  "meta": {
    "currency": "EUR",
    "exchange_rates_applied": [
      {
        "base_currency": "USD",
        "target_currency": "EUR",
        "rate": "0.870000000000000",
        "type": "static",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31"
      },
      {
        "base_currency": "USD",
        "target_currency": "EUR",
        "rate": "0.870000000000000",
        "type": "static",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28"
      },
      {
        "base_currency": "USD",
        "target_currency": "EUR",
        "rate": "0.870000000000000",
        "type": "static",
        "start_date": "2026-03-01",
        "end_date": "2026-03-31"
      },
      {
        "base_currency": "USD",
        "target_currency": "EUR",
        "rate": "0.910000000000000",
        "type": "dynamic",
        "start_date": "2026-04-01",
        "end_date": "2026-04-30"
      },
      {
        "base_currency": "GBP",
        "target_currency": "EUR",
        "rate": "1.170000000000000",
        "type": "dynamic",
        "start_date": "2026-03-01",
        "end_date": "2026-03-31"
      }
    ]
  }
}
```

**Implementation**: The response formatter queries `MonthlyExchangeRate` for
the report's date range and target currency
(see [pipeline-changes.md § Rate Resolution](./pipeline-changes.md#rate-resolution-strategy)).
Each `MonthlyExchangeRate` row produces one entry in the array with `start_date`
set to the first of the month and `end_date` to the last day of that month.
Consecutive months with the same rate and type are **not** grouped — each month
is returned as a separate entry.

Only base currencies that actually appear in the report's cost data are included.
For OCP reports, this means currencies from both `raw_currency` (infrastructure
costs) and cost model currencies are considered.

---

## OpenAPI

**File**: `koku/docs/specs/openapi.json`

Add endpoint definitions for:

- `GET /api/cost-management/v1/settings/currency/exchange_rate/` — list exchange rates grouped by currency (with enabled status)
- `POST /api/cost-management/v1/settings/currency/exchange_rate/` — create exchange rate
- `PUT /api/cost-management/v1/settings/currency/exchange_rate/{uuid}/` — update exchange rate
- `DELETE /api/cost-management/v1/settings/currency/exchange_rate/{uuid}/` — delete exchange rate
- `POST /api/cost-management/v1/settings/currency/exchange_rate/{code}/enable/` — enable currency
- `DELETE /api/cost-management/v1/settings/currency/exchange_rate/{code}/enable/` — disable currency

Add `exchange_rates_applied` to report response schemas.

Add error response schema for no-rate corner case (HTTP 400 with actionable
error message).

---

## Frontend Changes (Phase 1 — Backend Only)

Phase 1 focuses on the backend API. Frontend UI changes are tracked separately
and will consume the APIs defined above.

The frontend will:

- Add a currency exchange rate table in the Settings "Currency" tab, using
  `GET settings/currency/exchange_rate/` (grouped response with enabled status)
- Allow Price List Administrators to add, edit, and remove rate pairs
- Display validity periods (start/end month)
- Show a note explaining dynamic rates are used when no static rate is defined
- **Add a currency enablement toggle** using
  `POST/DELETE settings/currency/exchange_rate/{code}/enable/`
- **Populate the target currency dropdown** from enabled currencies only.
  Disabled currencies are stored but hidden from the report dropdown.
- **Handle the no-rate error**: When the user selects a target currency that
  has no conversion path from the bill currency, display the error message
  returned by the API
- **Handle no currencies available**: When no currencies are visible (all dynamic
  currencies disabled and no static rates), either hide the dropdown or show
  *"No exchange rates available"*

---

## Existing Components — No Changes

| Component | Reason |
|-----------|--------|
| Cost Model API (`/cost-models/`) | Unchanged; exchange rates are separate from cost model rates |
| Report endpoints (`/reports/...`) | Existing endpoints gain `exchange_rates_applied` metadata and no-rate error handling; no new report endpoints |
| Settings API (`/settings/`) — existing currency preference | Unchanged; the existing `UserSettings` currency display preference is separate from the new enablement API |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial API and frontend design |
| v1.1 | 2026-03-24 | Added currency enablement Settings API, available-currencies endpoint, dropdown behavior, no-rate corner case, airgapped UX |
| v1.2 | 2026-03-24 | Simplified enablement: `enabled` flag only controls dropdown visibility, not snapshotting. All currencies are always stored and snapshotted. |
| v1.3 | 2026-03-24 | Removed airgapped mode concept. Rate resolution: static first, dynamic fallback, error if neither. |
| v1.4 | 2026-03-26 | Updated report response implementation to reference two-tier rate resolution. |
| v1.5 | 2026-04-09 | Replaced stale `MonthlyExchangeRateSnapshot` → `MonthlyExchangeRate`, removed `StaticExchangeRateDictionary` references (removed in pipeline-changes v1.6). |
| v1.6 | 2026-04-12 | Updated `exchange_rates_applied` implementation to reflect `Subquery`-based rate resolution (removed `effective_exchange_rates` reference). |
| v1.7 | 2026-04-13 | Removed stale "snapshotted" terminology (remnant from `MonthlyExchangeRateSnapshot` rename). |
| v1.8 | 2026-04-28 | Consolidated endpoints under `settings/currency/exchange_rate/`. List returns grouped response with enabled status. Currency enablement via POST/DELETE (no body). Removed separate `AllCurrencyView` and `available-currencies` endpoints. |
| v1.9 | 2026-04-28 | Removed static-rate enablement bypass. Report dropdown governed solely by `EnabledCurrency`. Settings admin page shows static rates regardless for management. |
| v2.0 | 2026-04-28 | Added "costs as-is" behavior to Corner Case section: when `MonthlyExchangeRate` is empty, feature is inactive, costs returned in original currency. |
