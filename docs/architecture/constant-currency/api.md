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
| `GET` | `/settings/currency/` | Admin | All ISO currencies with enablement, dynamic availability, nested static rates |
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
`GET /settings/currency/` (`static_rates` nested under each base currency).

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

Administrator currency catalog for Settings UI.

**Permission:** settings access.

### Query parameters

| Param | Description |
|-------|-------------|
| `enabled` | `true` / `1` → only enabled; any other value → only disabled; omit → enabled first, then disabled |
| `search` | Case-insensitive substring match on currency `code` |
| `limit` / `offset` | Standard list pagination |

### Response item

```json
{
  "code": "USD",
  "name": "US Dollar",
  "symbol": "$",
  "description": "USD ($) - US Dollar",
  "enabled": true,
  "has_dynamic_rate": true,
  "static_rates": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "USD-EUR",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": "0.87",
      "start_date": "2026-04-01",
      "end_date": "2026-06-30",
      "created_timestamp": "2026-04-02T10:30:00Z",
      "updated_timestamp": "2026-04-02T10:30:00Z"
    }
  ]
}
```

`exchange_rate` is returned as a compact decimal string (trailing zeros
stripped). Full precision is retained in storage.

| Field | Meaning |
|-------|---------|
| `enabled` | Currency is enabled for the tenant |
| `has_dynamic_rate` | A dynamic (market) rate exists for this currency code |
| `static_rates` | Static rates where this currency is the **base** |

---

## `POST /settings/currency/enabled/{code}/`

Enable an ISO 4217 currency for the tenant.

**Permission:** settings access.

- `{code}` is normalized to uppercase.
- Invalid ISO codes → `400`.
- Idempotent: enabling an already-enabled currency returns `200`.

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
  "exchange_rate": "0.87",
  "start_date": "2026-04-01",
  "end_date": "2026-06-30"
}
```

#### Validation rules

| Rule | Error if violated |
|------|-------------------|
| Currencies are valid ISO 4217 codes | `400` |
| `base_currency != target_currency` | `400` |
| `exchange_rate > 0` | `400` |
| `start_date` is the 1st of a month | `400` |
| `end_date` is the last day of a month | `400` |
| `end_date >= start_date` | `400` |
| `start_date` not in a past month (for new rates / non-finalized updates) | `400` |
| No overlapping window for the same directional pair | `400` |

#### Response `201`

```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "USD-EUR",
  "base_currency": "USD",
  "target_currency": "EUR",
  "exchange_rate": "0.87",
  "start_date": "2026-04-01",
  "end_date": "2026-06-30",
  "created_timestamp": "2026-04-02T10:30:00Z",
  "updated_timestamp": "2026-04-02T10:30:00Z"
}
```

`name` is read-only: `"{base_currency}-{target_currency}"`.
`exchange_rate` in responses omits trailing zeros.

### `PUT /settings/currency/static-rates/{uuid}/`

Same body shape as create. Update rules:

- **`base_currency` cannot be changed** on any update (delete and recreate
  instead).
- When the rate already includes **finalized** months:
  - `target_currency` cannot change
  - `start_date` cannot change (shrink `end_date`, then create a new rate for
    the remaining period)
  - `end_date` cannot shrink earlier than the last day of the previous month
- Fully finalized rates (entire window before the current month) cannot be
  updated — create a new rate starting in the current month instead.

### `DELETE /settings/currency/static-rates/{uuid}/`

| Outcome | Status |
|---------|--------|
| Deleted | `204` |
| Entire window is finalized | `400` — cannot delete; create a new rate instead |

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
      "exchange_rate": "0.87",
      "rate_type": "static"
    },
    {
      "effective_date": "2026-05-01",
      "base_currency": "USD",
      "target_currency": "EUR",
      "exchange_rate": "0.91",
      "rate_type": "dynamic"
    }
  ]
}
```

`rate_type` is `static` or `dynamic`. Unknown schema or bad dates → `400`.

---

## Frontend consumption notes

| UI need | API |
|---------|-----|
| Target currency dropdown | `GET /currency/` |
| Settings currency table | `GET /settings/currency/` |
| Enable / disable toggle | `POST` / `DELETE` …`/enabled/{code}/` |
| Static rate form create/edit/delete | `POST` / `PUT` / `DELETE` …`/static-rates/…` |
| Show dynamic availability | `has_dynamic_rate` on settings list |
| Missing conversion | Surface report/forecast `400` `currency` error text |
| Empty dropdown | No enabled currencies → hide picker or show “No exchange rates available” |
