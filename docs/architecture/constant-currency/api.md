# Constant Currency APIs

Public Cost Management APIs and the internal Masu inspection endpoint for
constant currency. Base path unless noted:

```
/api/cost-management/v1/
```

---

## Endpoint map

| Method | Path | Audience | Purpose |
|--------|------|----------|---------|
| `GET` | `/currency/` | End user | Enabled currencies for the target-currency dropdown |
| `GET` | `/settings/currency/` | Admin | Current tender ISO currencies with enablement, dynamic availability, nested static rates; CSV export of flat static rates via `Accept: text/csv` |
| `POST` | `/settings/currency/enabled/{code}/` | Admin | Enable a currency |
| `DELETE` | `/settings/currency/enabled/{code}/` | Admin | Disable a currency |
| `POST` | `/settings/currency/static-rates/` | Price list admin | Create a static exchange rate |
| `PUT` | `/settings/currency/static-rates/{uuid}/` | Price list admin | Update a static exchange rate |
| `DELETE` | `/settings/currency/static-rates/{uuid}/` | Price list admin | Delete a static exchange rate |
| `GET` | `/monthly_exchange_rates/` | Internal (Masu) | Inspect stored monthly rates for a tenant schema |

Report and forecast endpoints are unchanged in shape. With the constant-currency
flag on, they convert using per-month rates and may return `400` when coverage
is incomplete (see [Report and forecast behavior](#report-and-forecast-behavior)).

There is **no** dedicated `GET` collection for static rates; list them via
`GET /settings/currency/` (`static_rates` nested under each base currency), or
export them as a flat CSV with `Accept: text/csv` on the same endpoint.

---

## `GET /currency/`

Returns currencies enabled for the tenant. Used by the target-currency dropdown.

**Permission:** authenticated user.

### Response (paginated)

```json
{
  "meta": { "count": 2 },
  "data": [
    {
      "code": "USD",
      "name": "US Dollar",
      "symbol": "$",
      "description": "USD ($) - US Dollar"
    },
    {
      "code": "EUR",
      "name": "Euro",
      "symbol": "€",
      "description": "EUR (€) - Euro"
    }
  ]
}
```

Only enabled currencies appear. Name/symbol/description are derived from the
ISO 4217 registry at response time.

---

## `GET /settings/currency/`

Administrator currency catalog for Settings UI. Lists **current tender** ISO
4217 currencies (babel territory data). Already-enabled inactive/withdrawn
codes remain in the list so they can be disabled.

**Permission:** settings access.

### Query parameters

| Param | Description |
|-------|-------------|
| `filter[enabled]` | **JSON:** `true` / `1` → only enabled; `false` / `0` → only disabled current-tender; omit → active tender ∪ enabled. **CSV:** keep rates whose **base** currency is enabled (`true`/`1`) or disabled (`false`/`0`); omit → all static rates |
| `filter[currency]` | Case-insensitive substring match (comma-separated / repeated params = OR). **JSON:** matches the currency catalog `code` (base). **CSV:** matches a rate if the term appears in **base or target** currency (e.g. `EUR` includes USD→EUR). Non-matching values return an empty list |
| `order_by[code]` | **JSON:** `asc` (default) or `desc` — sort catalog by ISO currency code. **CSV:** unused (rates are ordered by base, target, start_date) |
| `limit` / `offset` | Standard list pagination (**JSON only**; CSV ignores pagination) |

### Response item

```json
{
  "code": "USD",
  "name": "US Dollar",
  "symbol": "$",
  "description": "USD ($) - US Dollar",
  "enabled": true,
  "has_dynamic_rate": true,
  "active_rate_type": "static",
  "static_rates": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "USD-EUR",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": 0.87,
      "start_date": "2026-10-01",
      "end_date": "2026-12-31",
      "created_timestamp": "2026-10-02T10:30:00Z",
      "updated_timestamp": "2026-10-02T10:30:00Z"
    }
  ]
}
```

`exchange_rate` is returned as a JSON number. Storage retains full
`DecimalField` precision; typical clients parse JSON numbers as IEEE 754
doubles (~15–17 significant digits).

**Units / direction:** `exchange_rate` is a **base → target** multiplier —
units of `target_currency` per 1 unit of `base_currency`. Example:
`base_currency=AED`, `target_currency=EUR`, `exchange_rate=0.92` means
**1 AED = 0.92 EUR** (conversion: `amount_in_base × exchange_rate →
amount_in_target`). For UI formatting, use `target_currency` as the units
(display `0.92 EUR`). There is no separate `exchange_rate_units` field;
that would always equal `target_currency`.

| Field | Meaning |
|-------|---------|
| `enabled` | Currency is enabled for the tenant |
| `has_dynamic_rate` | A dynamic (market) rate exists for this currency code |
| `active_rate_type` | Rate in force **this UTC month**: `static`, `dynamic`, or `none` |
| `static_rates` | Static rates where this currency is the **base** |

`active_rate_type` is computed (not stored):

| Value | When |
|-------|------|
| `static` | Enabled, and at least one static rate for this base overlaps the current UTC month (wins over dynamic) |
| `dynamic` | Enabled, no current-month static, and `has_dynamic_rate` is true |
| `none` | Disabled, or enabled with neither a current-month static nor a dynamic rate |

CSV export does **not** include `active_rate_type`.

### CSV export (`Accept: text/csv`)

Same path; response is a **flat, unpaginated** CSV of static exchange rates
(not the ISO currency catalog). Nested `static_rates` arrays are expanded into
one row per rate. Columns (stable order): `base_currency`, `target_currency`,
`exchange_rate`, `start_date`, `end_date`, `uuid`, `name`. Empty exports still
include the header row.

Filter params are reused but **do not mean the same thing as in JSON**:

| Param | JSON | CSV |
|-------|------|-----|
| `filter[currency]` | Match catalog `code` (base currency only) | Match rate **base or target** |
| `filter[enabled]` | Include/exclude currency catalog rows by enablement | Keep rates whose **base** is enabled/disabled |
| `order_by[code]` | Sort catalog `asc`/`desc` (default `asc`) | Unused |
| `limit` / `offset` | Paginate catalog | Ignored (full matching set) |

Example: `filter[currency]=EUR` returns the EUR catalog entry in JSON, but in CSV
includes rates such as USD→EUR. Tenant enablement flags are not CSV columns.

JSON behavior for `Accept: application/json` is unchanged. Implementation:
[`CurrencySettingsView`](../../../koku/api/settings/currency_views.py).

---

## `POST /settings/currency/enabled/{code}/`

Enable a **current tender** ISO 4217 currency for the tenant.

**Permission:** settings access.

- `{code}` is normalized to uppercase.
- Inactive / non-tender / invalid ISO codes (e.g. `XXX`, withdrawn `FRF`) → `400`
  (including when that code is already enabled — active-tender validation runs
  before `get_or_create`).
- Idempotent for **current tender** codes only: enabling an already-enabled
  current-tender currency returns `200`.

**Success:** `200` with empty body.

**Side effects (product behavior):** current-month dynamic monthly rates for
pairs involving this currency are populated when market data is available;
report caches for the tenant are invalidated.

---

## `DELETE /settings/currency/enabled/{code}/`

Disable a currency.

**Permission:** settings access.

| Outcome | Status | Body |
|---------|--------|------|
| Disabled successfully | `204` | empty |
| Already disabled (idempotent) | `204` | empty |
| Would remove the last enabled currency | `400` | `{ "error": "At least one currency must be enabled." }` |
| Currency is in use / is a default | `400` | structured error + affected lists |
| Invalid code | `400` | validation error |

Disable is **rejected** when any of these apply:

- It is the system default currency
- It is the account default currency
- Cloud provider billing data uses it as a base currency
- One or more cost models use it
- One or more price lists use it

### Blocked response example

```json
{
  "errors": [
    {
      "detail": "Cannot disable GBP because it is used by 1 cost model(s).",
      "source": "currency",
      "status": 400
    }
  ],
  "affected_cloud_providers": [],
  "affected_cost_models": [
    { "uuid": "...", "name": "GBP Cost Model" }
  ],
  "affected_price_lists": []
}
```

On successful disable, current-month monthly rates involving the currency are
removed (past months stay finalized).

---

## Static exchange rates

**Permission:** cost models / price list access.

### `POST /settings/currency/static-rates/`

#### Request

```json
{
  "base_currency": "USD",
  "target_currency": "EUR",
  "exchange_rate": 0.87,
  "start_date": "2026-04-01",
  "end_date": "2026-06-30"
}
```

`exchange_rate` must be the **base → target** multiplier (target per 1 base).
Same semantics as on `GET /settings/currency/` (see units note above).

#### Validation rules

| Rule | Error if violated |
|------|-------------------|
| Currencies are valid ISO 4217 codes | `400` |
| `base_currency != target_currency` | `400` |
| `exchange_rate > 0` | `400` |
| `start_date` is the 1st of a month | `400` |
| `end_date` is the last day of a month | `400` |
| `end_date >= start_date` | `400` |
| No overlapping window for the same directional pair | `400` |

Note: `base_currency` and `target_currency` do not need to be enabled at the
time of creation. Admins may pre-configure static rates before enabling a
currency for end users.

#### Response `201`

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "USD-EUR",
  "base_currency": "USD",
  "target_currency": "EUR",
  "exchange_rate": 0.87,
  "start_date": "2026-04-01",
  "end_date": "2026-06-30",
  "created_timestamp": "2026-04-02T10:30:00Z",
  "updated_timestamp": "2026-04-02T10:30:00Z"
}
```

`name` is read-only: `"{base_currency}-{target_currency}"`.
`exchange_rate` in responses is a JSON number (see settings list note above).

### `PUT /settings/currency/static-rates/{uuid}/`

Same body shape as create. Update rules:

- **`base_currency` cannot be changed** on any update (delete and recreate
  instead).
- Past-month windows are allowed: target, start/end dates, and rate may change.
  STATIC `MonthlyExchangeRate` rows are rewritten for each affected month from
  retention through the current month. Finalized **dynamic** monthly rates are
  not rewritten by static CRUD except when a static override for that pair/month
  is removed and dynamic rates are restored.

### `DELETE /settings/currency/static-rates/{uuid}/`

| Outcome | Status |
|---------|--------|
| Deleted | `204` |

Past-month rates may be deleted. STATIC monthly overrides in the window are
removed and dynamic rates are restored when possible.

---

## Report and forecast behavior

Existing report/forecast URLs are unchanged. Relevant product behavior when
`cost-management.backend.constant-currency` is on for the tenant:

1. Conversion uses the monthly rate for each usage month:
   `source currency → requested currency`.
2. OCP reports/forecasts continue to distinguish:
   - cost-model currency conversion
   - infrastructure / cloud-bill currency conversion
3. Before returning data, the API checks that every required base currency has a
   monthly rate for **every month** in the query range.
4. Missing coverage → `400`:

```json
{
  "errors": [
    {
      "currency": "No exchange rate available for USD -> EUR for 2026-01-01 to 2026-03-31. Ask your administrator to configure static exchange rates or enable dynamic exchange rates."
    }
  ]
}
```

(When `CURRENCY_URL` is configured, the message may omit the “or enable dynamic
exchange rates” clause and point administrators at static rates.)

Same-currency conversion (base equals target) uses rate `1`.

---

## `GET /monthly_exchange_rates/` (Masu)

Internal inspection of stored monthly rates.

**Typical path:** Masu API root + `monthly_exchange_rates/`.

### Query parameters

| Param | Required | Description |
|-------|----------|-------------|
| `schema` | yes | Tenant schema name |
| `start_date` | no | `YYYY-MM-DD`, `effective_date >=` |
| `end_date` | no | `YYYY-MM-DD`, `effective_date <=` |
| `base_currency` | no | Filter |
| `target_currency` | no | Filter |

### Response

```json
{
  "count": 2,
  "rates": [
    {
      "effective_date": "2026-04-01",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": 0.87,
      "rate_type": "static"
    },
    {
      "effective_date": "2026-05-01",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": 0.91,
      "rate_type": "dynamic"
    }
  ]
}
```

`rate_type` is `static` or `dynamic`. `exchange_rate` is a JSON number
(same representation and base → target units semantics as Settings
static-rate responses). Unknown schema or bad dates → `400`.

---

## Frontend consumption notes

| UI need | API |
|---------|-----|
| Target currency dropdown | `GET /currency/` |
| Settings currency table | `GET /settings/currency/` |
| Active rate (this month) | If `enabled` is false, show Not enabled. Otherwise use `active_rate_type`: Static / Dynamic / None |
| Enable / disable toggle | `POST` / `DELETE` …`/enabled/{code}/` |
| Static rate form create/edit/delete | `POST` / `PUT` / `DELETE` …`/static-rates/…` |
| Show dynamic availability | `has_dynamic_rate` on settings list |
| Missing conversion | Surface report/forecast `400` `currency` error text |
| Empty dropdown | No enabled currencies → hide picker or show “No exchange rates available” |
