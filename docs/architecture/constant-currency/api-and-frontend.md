# API and Frontend Changes

API and frontend modifications for the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)). Covers the new
CRUD endpoint for static exchange rates, report response enhancements, and
OpenAPI updates.

---

## Exchange Rate Endpoint

### URL

```
GET             /api/cost-management/v1/settings/currency/
POST            /api/cost-management/v1/settings/currency/exchange-rates/
PUT/DELETE      /api/cost-management/v1/settings/currency/exchange-rates/{uuid}/
POST/DELETE     /api/cost-management/v1/settings/currency/enabled/{code}/
```

### Registration

**File**: `koku/api/urls.py`

Registered as explicit `path()` entries: `settings/currency/` for the currency
list, `settings/currency/exchange-rates/` for static rate CRUD, and
`settings/currency/enabled/{code}/` for enablement toggling.

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `base_currency` | string | Filter by base currency code (e.g., `USD`) |
| `target_currency` | string | Filter by target currency code (e.g., `EUR`) |
| `start_date` | date | Filter rates active on or after this date |
| `end_date` | date | Filter rates active on or before this date |
| `search` | string | Filter currencies by code or name (case-insensitive substring) |
| `enabled` | boolean | Filter by enabled status (`true` or `false`) |

### Views

**File**: `koku/api/settings/currency_views.py`

The `CurrencyListView` handles the `GET settings/currency/` endpoint. It
returns all ISO 4217 currencies (~170) grouped by base currency, each with an
`enabled` flag, `has_dynamic_rate` flag, `description` string, and a nested
`exchange_rates` array of static rates. Supports `?search=` and `?enabled=`
query params for filtering.

**Permission**: `SettingsAccessPermission` — requires the **Cost Management
Administrator** role.

**File**: `koku/cost_models/static_exchange_rate_view.py`

The `StaticExchangeRateViewSet` handles create, update, and delete for static
exchange rates. It exposes only `POST`, `PUT`, and `DELETE` methods (no `GET`
— the list view is separate). Uses `CostModelsAccessPermission` — requires
the **Price List Administrator** role.

**File**: `koku/api/settings/currency_views.py`

The `EnabledCurrencyView` handles currency enablement via POST (enable) and
DELETE (disable). No request body required. On DELETE, it also cleans up
dynamic `MonthlyExchangeRate` rows for the current month where the currency
appears as base or target.

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

The list endpoint returns exchange rates grouped by base currency. Each
currency entry includes its enabled status and a nested list of exchange rates.
Only currencies with at least one `StaticExchangeRate` record appear.

```json
{
  "meta": { "count": 1 },
  "data": [
    {
      "code": "USD",
      "name": "US Dollar",
      "symbol": "$",
      "description": "USD ($) - US Dollar",
      "has_dynamic_rate": true,
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
        },
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

Currency enablement is toggled via POST/DELETE on a per-currency endpoint.
Currency discovery (browsing all currencies with their enabled status) is
provided by `GET settings/currency/`, which returns all ISO 4217
currencies.

### URL

```
POST    /api/cost-management/v1/settings/currency/enabled/{code}/
DELETE  /api/cost-management/v1/settings/currency/enabled/{code}/
```

- **POST**: Enables the currency (creates an `EnabledCurrency` row). No request body.
- **DELETE**: Disables the currency (removes the `EnabledCurrency` row). No request body.

POST returns `200 OK` (with optional warning). DELETE returns `204 No Content`.

### View

**File**: `koku/api/settings/currency_views.py` — `EnabledCurrencyView`

**Permission**: `SettingsAccessPermission` — requires the **Cost Management
Administrator** role.

**Side effects**:
- **POST (enable)**: Creates an `EnabledCurrency` row. Returns a warning if no
  exchange rate is available for the currency.
- **DELETE (disable)**: Removes the `EnabledCurrency` row and deletes dynamic
  `MonthlyExchangeRate` rows for the current month where the currency appears
  as base or target. Does not affect `ExchangeRateDictionary`, `ExchangeRates`,
  or `StaticExchangeRate` tables.

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

### Currency Discovery

The `GET settings/currency/` endpoint returns all ISO 4217
currencies (~170) with their enabled status. The UI uses this as the source of
truth for currency discovery — administrators can search for any currency and
enable it. Use `?search=` for autocomplete/typeahead filtering and `?enabled=`
to show only enabled or disabled currencies.

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
task run), the constant currency feature is inactive. No currencies are enabled,
so the serializer rejects any explicit `currency` parameter — the user cannot
select a target currency. Without a `currency` parameter, costs are returned
as-is in their original bill currency. The `Coalesce("exchange_rate", Value(1))`
fallback in provider maps ensures NULL annotations resolve to `1` (no
conversion). This is the default state for fresh deployments.

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

- `GET /api/cost-management/v1/settings/currency/` — list all ISO 4217 currencies with exchange rates and enabled status (supports `?search=`, `?enabled=`)
- `POST /api/cost-management/v1/settings/currency/exchange-rates/` — create static exchange rate
- `PUT /api/cost-management/v1/settings/currency/exchange-rates/{uuid}/` — update static exchange rate
- `DELETE /api/cost-management/v1/settings/currency/exchange-rates/{uuid}/` — delete static exchange rate
- `POST /api/cost-management/v1/settings/currency/enabled/{code}/` — enable currency
- `DELETE /api/cost-management/v1/settings/currency/enabled/{code}/` — disable currency

Add `exchange_rates_applied` to report response schemas.

Add error response schema for no-rate corner case (HTTP 400 with actionable
error message).

---

## Frontend Changes (Phase 1 — Backend Only)

Phase 1 focuses on the backend API. Frontend UI changes are tracked separately
and will consume the APIs defined above.

The frontend will:

- Add a currency exchange rate table in the Settings "Currency" tab, using
  `GET settings/currency/` (all currencies with enabled status and exchange rates)
- Allow Price List Administrators to add, edit, and remove rate pairs
- Display validity periods (start/end month)
- Show a note explaining dynamic rates are used when no static rate is defined
- **Add a currency enablement toggle** using
  `POST/DELETE settings/currency/enabled/{code}/`
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
| v1.8 | 2026-04-28 | Consolidated endpoints under `settings/currency/exchange-rates/`. List returns grouped response with enabled status. Currency enablement via POST/DELETE at `settings/currency/enabled/{code}/` (no body). Removed separate `AllCurrencyView` and `available-currencies` endpoints. |
| v1.9 | 2026-04-28 | Removed static-rate enablement bypass. Report dropdown governed solely by `EnabledCurrency`. Settings admin page shows static rates regardless for management. |
| v2.0 | 2026-04-28 | Added "costs as-is" behavior to Corner Case section: when `MonthlyExchangeRate` is empty, feature is inactive, costs returned in original currency. |
| v2.1 | 2026-04-30 | Fixed currency enablement URLs to `settings/currency/enabled/{code}/`. Clarified "costs as-is" Corner Case: serializer enforces enabled currencies before query handler validation. |
| v2.2 | 2026-06-02 | `GET enabled-currencies/` now returns all ISO 4217 currencies with `enabled` flag. Added `?search` and `?enabled` query params. `GET exchange-rates/` list now includes enabled currencies with no static rates. |
| v2.3 | 2026-06-03 | Removed `GET enabled-currencies/` endpoint. Restructured URLs: `GET settings/currency/` returns all ISO 4217 currencies (with `?search=`, `?enabled=`), `settings/currency/exchange-rates/` for static rate CRUD, `settings/currency/enabled/{code}/` for enablement toggling. |
| v2.4 | 2026-06-03 | Synced with implementation: `GET settings/currency/` is `CurrencyListView` (SettingsAccessPermission), not `StaticExchangeRateViewSet`. ViewSet exposes POST/PUT/DELETE only (no GET). EnabledCurrency DELETE also cleans up dynamic MER rows. Added `description` and `has_dynamic_rate` to response example. Fixed changelog URL inconsistencies. |
