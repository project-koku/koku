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

**Side effects** (see [pipeline-changes.md § Writer 2](./pipeline-changes.md#static-rate--snapshot--dictionary--writer-2)):

All side effects are wrapped in a database transaction (`transaction.atomic()`)
together with the `StaticExchangeRate` write. If any side effect fails, the
`StaticExchangeRate` change is rolled back, preventing an inconsistent state.

- **On create/update**:
  1. Writes `rate_type=RateType.STATIC` rows to `MonthlyExchangeRateSnapshot`
     for each affected month
  2. Rebuilds `StaticExchangeRateDictionary` from all `StaticExchangeRate` rows
- **On delete**:
  1. Removes `rate_type=RateType.STATIC` rows for affected months, then
     proactively populates `rate_type=RateType.DYNAMIC` rows from the current
     `ExchangeRateDictionary` to avoid a data gap until the next daily Celery run
  2. Rebuilds `StaticExchangeRateDictionary` from remaining `StaticExchangeRate`
     rows (the deleted rate is excluded from the matrix)

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
GET/PUT   /api/cost-management/v1/settings/currency/enabled-currencies/
```

This endpoint lists all known currencies and their enabled/disabled status, and
allows an administrator to enable or disable currencies.

### View

**File**: Extend existing settings views in `koku/api/settings/` or add a new
`EnabledCurrencyViewSet`.

**Permission**: Cost Management Administrator role (same permission level as
other Settings operations).

### Example: GET Response

```json
{
  "meta": { "count": 5 },
  "data": [
    { "currency_code": "USD", "enabled": true },
    { "currency_code": "EUR", "enabled": true },
    { "currency_code": "GBP", "enabled": false },
    { "currency_code": "CNY", "enabled": false },
    { "currency_code": "JPY", "enabled": false }
  ]
}
```

Currencies with `enabled: false` were discovered by the daily exchange rate API
fetch but have not been enabled by an administrator. They will not be used for
dynamic exchange rate conversions until enabled.

### Example: PUT Request (Enable/Disable)

```json
{
  "currencies": [
    { "currency_code": "GBP", "enabled": true },
    { "currency_code": "CNY", "enabled": true }
  ]
}
```

**Side effects**: When a currency is enabled, the next daily Celery task run
will begin snapshotting dynamic exchange rates for pairs involving that
currency. When disabled, future snapshots will skip pairs involving that
currency (existing snapshots are not removed).

### Airgapped Mode (No `CURRENCY_URL`)

When no `CURRENCY_URL` is configured, the `EnabledCurrency` table will have no
dynamically-discovered currencies. The GET response will return either an empty
list or only currencies that were manually added. The Settings UI should indicate
that dynamic exchange rates are unavailable and only static exchange rates can be
used.

---

## Available Currencies for Dropdown

The target currency dropdown in the UI must compute its list of available
currencies from two sources:

### Availability Rules

| Source | Rule | Example |
|--------|------|---------|
| **Dynamic** | Currency has `enabled=True` in `EnabledCurrency` AND has exchange rates in `MonthlyExchangeRateSnapshot` or `ExchangeRateDictionary` | USD, EUR enabled → appear in dropdown |
| **Static** | Currency appears in any `StaticExchangeRate` pair (as base or target) | Static rate EUR→CHF defined → both EUR and CHF appear in dropdown regardless of `EnabledCurrency` status |

### Dropdown Endpoint

**File**: New endpoint or extend existing currency-related views.

```
GET /api/cost-management/v1/settings/currency/available-currencies/
```

Returns the union of enabled dynamic currencies and static rate currencies:

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

- No `CURRENCY_URL` is configured (no dynamic rates), **and**
- No `StaticExchangeRate` rows exist (no static rates), **and/or**
- All currencies in `EnabledCurrency` are disabled

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

**Implementation**: The query handler's `effective_exchange_rates` property
(see [pipeline-changes.md § Reader](./pipeline-changes.md#modified-query-handler--reader))
provides the snapshot rows. The response formatter groups consecutive months
with the same rate and type into a single entry with `start_date` / `end_date`
boundaries (first-of-month and last-day-of-month respectively).

---

## OpenAPI

**File**: `koku/docs/specs/openapi.json`

Add endpoint definitions for:

- `GET /api/cost-management/v1/exchange-rate-pairs/` — list with filters
- `POST /api/cost-management/v1/exchange-rate-pairs/` — create
- `GET /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — retrieve
- `PUT /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — update
- `DELETE /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — delete
- `GET /api/cost-management/v1/settings/currency/enabled-currencies/` — list enabled/disabled currencies
- `PUT /api/cost-management/v1/settings/currency/enabled-currencies/` — enable/disable currencies
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
  endpoint (union of enabled dynamic + static rate currencies)
- **Handle the no-rate error**: When the user selects a target currency that
  has no conversion path from the bill currency, display the error message
  returned by the API
- **Handle no currencies available**: When no currencies are available at all
  (airgapped mode with no static rates, or all currencies disabled), either
  hide the dropdown or show *"No exchange rates available"*

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
