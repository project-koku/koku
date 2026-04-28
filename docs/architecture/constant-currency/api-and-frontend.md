# API and Frontend Changes

API and frontend modifications for the Constant Currency feature
([COST-7252](https://redhat.atlassian.net/browse/COST-7252)). Covers the new
CRUD endpoint for static exchange rates, report response enhancements, and
OpenAPI updates.

---

## New CRUD Endpoint: Exchange Rate Pairs

### URL

```
GET/POST        /api/cost-management/v1/exchange-rate-pairs/
GET/PUT/DELETE   /api/cost-management/v1/exchange-rate-pairs/{uuid}/
```

### Registration

**File**: `koku/cost_models/urls.py`

Register `StaticExchangeRateViewSet` on the existing `DefaultRouter` as
`"exchange-rate-pairs"`.

```python
router.register(r"exchange-rate-pairs", StaticExchangeRateViewSet, basename="exchange-rate-pairs")
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `base_currency` | string | Filter by base currency code (e.g., `USD`) |
| `target_currency` | string | Filter by target currency code (e.g., `EUR`) |
| `start_date` | date | Filter rates active on or after this date |
| `end_date` | date | Filter rates active on or before this date |

### View

**File**: New `koku/cost_models/static_exchange_rate_view.py`

```python
class StaticExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = StaticExchangeRate.objects.all()
    serializer_class = StaticExchangeRateSerializer
    lookup_field = "uuid"
    permission_classes = (CostModelsAccessPermission,)
```

Follows the pattern from `CostModelViewSet` in `koku/cost_models/view.py`.
All operations run under tenant context (handled by `django-tenants` middleware).

**Permission**: `CostModelsAccessPermission` — requires the **Price List
Administrator** role. Same permission used for cost model CRUD.

### Serializer

**File**: New `koku/cost_models/static_exchange_rate_serializer.py`

**Validation rules**:

| Rule | Description |
|------|-------------|
| Currency codes | `base_currency` and `target_currency` must be in `VALID_CURRENCIES` |
| Different currencies | `base_currency != target_currency` |
| Month boundaries | `start_date` must be 1st of month; `end_date` must be last day of a month |
| No overlap | No overlapping validity periods for same directional `(base, target)` pair |
| Version | Auto-increment `version` on update |
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

### Example: List Response

```json
{
  "meta": { "count": 2 },
  "data": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "USD-EUR",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": "0.870000000000000",
      "start_date": "2026-01-01",
      "end_date": "2026-03-31",
      "version": 1,
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
      "version": 2,
      "created_timestamp": "2026-01-15T10:30:00Z",
      "updated_timestamp": "2026-02-01T14:00:00Z"
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

## Currency Enablement Settings API

### URL

```
GET/PUT   /api/cost-management/v1/settings/currency/config/
```

This endpoint lists all known currencies and their enabled/disabled status, and
allows an administrator to enable or disable currencies.

### View

**File**: `koku/api/settings/currency_views.py` — `EnabledCurrencyView` (PUT to toggle enabled/disabled).
**File**: `koku/cost_models/static_exchange_rate_view.py` — `StaticExchangeRateViewSet` (GET list returns currencies grouped with exchange rates and enabled status).

**Permission**: Cost Management Administrator role (same permission level as
other Settings operations).

### Example: GET `settings/currency/` Response

Returns all ISO 4217 currencies (from Babel) with an `enabled` flag based on
`EnabledCurrency` table membership.

```json
{
  "meta": { "count": 300 },
  "data": [
    { "code": "AED", "name": "UAE Dirham", "symbol": "AED", "description": "...", "enabled": false },
    { "code": "EUR", "name": "Euro", "symbol": "€", "description": "...", "enabled": true },
    { "code": "USD", "name": "US Dollar", "symbol": "$", "description": "...", "enabled": true }
  ]
}
```

### Example: POST `settings/currency/config/` Request (Bulk Set)

Replaces all enabled currencies atomically with the submitted list.

```json
{
  "currencies": ["USD", "EUR", "GBP"]
}
```

Response: `204 No Content`

**Side effects**: Enabling or disabling a currency only affects its visibility
in the target currency dropdown. It does not affect the `MonthlyExchangeRate`,
`ExchangeRateDictionary`, `ExchangeRates`, or `StaticExchangeRate` tables.

### No `CURRENCY_URL` Configured

When no `CURRENCY_URL` is configured, no dynamic exchange rates are fetched by
the Celery task. The `EnabledCurrency` table only contains currencies that an
administrator has explicitly enabled via the Settings API. The full list of
ISO 4217 currencies is always available from Babel.

---

## Available Currencies for Dropdown

The target currency dropdown in the UI must compute its list of available
currencies from two sources:

### Availability Rules

| Source | Rule | Example |
|--------|------|---------|
| **Dynamic** | Currency exists in `EnabledCurrency` table | USD, EUR enabled → appear in dropdown |
| **Static** | Currency appears in any `StaticExchangeRate` pair (as base or target) | Static rate EUR→CHF defined → both EUR and CHF appear in dropdown regardless of `EnabledCurrency` status |

### Dropdown Endpoint

**File**: New endpoint or extend existing currency-related views.

```
GET /api/cost-management/v1/settings/currency/available-currencies/
```

Returns the currencies visible to the user — the union of enabled dynamic
currencies and static rate currencies:

```json
{
  "data": [
    { "currency_code": "USD", "source": "dynamic" },
    { "currency_code": "EUR", "source": "both" },
    { "currency_code": "CHF", "source": "static" },
    { "currency_code": "GBP", "source": "dynamic" }
  ]
}
```

The `source` field indicates whether the currency is available via dynamic rates,
static rates, or both. This is informational for the frontend.

### No Currencies Available

When **no currencies are available at all** — meaning:

- No currencies exist in `EnabledCurrency` (none enabled), **and**
- No `StaticExchangeRate` rows exist (no static rates)

Then the currency dropdown should either be **hidden** or show a message:
*"No exchange rates available."* Whichever approach is simpler to implement.

---

## Corner Case: No Exchange Rate

A currency may appear in the dropdown (because it has static or enabled dynamic
rates) but have **no exchange rate path** from the bill's source currency to
the selected target currency.

**Example**:
- Cloud bill arrives in `USD`
- Static rates define `EUR↔CHF` and `CNY↔SAR`
- User wants to see costs in `EUR`
- There is no `USD→EUR` rate (static or dynamic)

### Behavior (Preferred Approach)

**Make all available currencies visible** in the dropdown (`EUR`, `CHF`, `CNY`,
`SAR`), but when the user selects a target currency for which no conversion rate
exists from the bill currency, the API returns an error:

```json
{
  "errors": [
    {
      "detail": "No exchange rate available between USD and EUR. Ask your administrator to configure static exchange rates or enable dynamic exchange rates.",
      "status": 400,
      "source": "currency"
    }
  ]
}
```

The frontend should display this error message to the user. The report data is
**not** returned with unconverted amounts — the request fails with a clear,
actionable error.

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
(see [pipeline-changes.md § Rate Resolution](./pipeline-changes.md#rate-resolution-strategy)),
then groups consecutive months with the same rate and type into a single entry
with `start_date` / `end_date` boundaries (first-of-month and last-day-of-month
respectively).

---

## OpenAPI

**File**: `koku/docs/specs/openapi.json`

Add endpoint definitions for:

- `GET /api/cost-management/v1/exchange-rate-pairs/` — list with filters
- `POST /api/cost-management/v1/exchange-rate-pairs/` — create
- `GET /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — retrieve
- `PUT /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — update
- `DELETE /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — delete
- `GET /api/cost-management/v1/settings/currency/config/` — list enabled/disabled currencies
- `PUT /api/cost-management/v1/settings/currency/config/` — enable/disable currencies
- `GET /api/cost-management/v1/settings/currency/available-currencies/` — list available target currencies

Add `exchange_rates_applied` to report response schemas.

Add error response schema for no-rate corner case (HTTP 400 with actionable
error message).

---

## Frontend Changes (Phase 1 — Backend Only)

Phase 1 focuses on the backend API. Frontend UI changes are tracked separately
and will consume the APIs defined above.

The frontend will:

- Add a currency exchange rate table in the Settings "Currency" tab
- Allow Price List Administrators to add, edit, and remove rate pairs
- Display validity periods (start/end month)
- Show a note explaining dynamic rates are used when no static rate is defined
- **Add a currency enablement section** in Settings for enabling/disabling
  currencies discovered from the exchange rate API
- **Populate the target currency dropdown** from the available-currencies
  endpoint (union of enabled dynamic currencies + static rate currencies).
  Disabled currencies are stored but hidden from this dropdown.
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
