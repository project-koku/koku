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
        "period": "2026-01 to 2026-03"
      },
      {
        "base_currency": "USD",
        "target_currency": "EUR",
        "rate": "0.910000000000000",
        "type": "dynamic",
        "period": "2026-04"
      },
      {
        "base_currency": "GBP",
        "target_currency": "EUR",
        "rate": "1.170000000000000",
        "type": "dynamic",
        "period": "2026-03"
      }
    ]
  }
}
```

**Implementation**: The query handler's `effective_exchange_rates` property
(see [pipeline-changes.md § Reader](./pipeline-changes.md#modified-query-handler--reader))
provides the snapshot rows. The response formatter groups consecutive months
with the same rate and type into a single `period` string.

---

## OpenAPI

**File**: `koku/docs/specs/openapi.json`

Add endpoint definitions for:

- `GET /api/cost-management/v1/exchange-rate-pairs/` — list with filters
- `POST /api/cost-management/v1/exchange-rate-pairs/` — create
- `GET /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — retrieve
- `PUT /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — update
- `DELETE /api/cost-management/v1/exchange-rate-pairs/{uuid}/` — delete

Add `exchange_rates_applied` to report response schemas.

---

## Frontend Changes (Phase 1 — Backend Only)

Phase 1 focuses on the backend API. Frontend UI changes (Settings page
"Currency" tab with exchange rate table, add/edit/remove buttons) are tracked
separately and will consume the API defined above.

The frontend will:

- Add a currency exchange rate table in the Settings "Currency" tab
- Allow Price List Administrators to add, edit, and remove rate pairs
- Display validity periods (start/end month)
- Show a note explaining dynamic rates are used when no static rate is defined

---

## Existing Components — No Changes

| Component | Reason |
|-----------|--------|
| Cost Model API (`/cost-models/`) | Unchanged; exchange rates are separate from cost model rates |
| Report endpoints (`/reports/...`) | Existing endpoints gain `exchange_rates_applied` metadata; no new endpoints |
| Settings API (`/settings/`) | Unchanged; currency display preference remains in UserSettings |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-19 | Initial API and frontend design |
