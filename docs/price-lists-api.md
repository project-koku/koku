# Price Lists API

Price Lists are a new standalone resource that allows you to define reusable sets of OCP rates
with a validity period, versioning, and enabled/disabled control. They are designed to be
attached to Cost Models and work as an on-prem feature.

**Base URL:** `GET /api/cost-management/v1/price-lists/`

---

## Table of Contents

- [Data Model](#data-model)
- [Endpoints](#endpoints)
  - [List](#list-get-apicost-managementv1price-lists)
  - [Create](#create-post-apicost-managementv1price-lists)
  - [Retrieve](#retrieve-get-apicost-managementv1price-listsuuid)
  - [Update](#update-put-apicost-managementv1price-listsuuid)
  - [Delete](#delete-delete-apicost-managementv1price-listsuuid)
  - [Affected Cost Models](#affected-cost-models-get-apicost-managementv1price-listsuuidaffected-cost-models)
- [Filtering](#filtering)
- [Ordering](#ordering)
- [Pagination](#pagination)
- [Rate Formats](#rate-formats)
- [Supported Metrics](#supported-metrics)
- [Versioning Behavior](#versioning-behavior)
- [Known Limitations](#known-limitations)

---

## Data Model

| Field | Type | Read-only | Required | Description |
|---|---|---|---|---|
| `uuid` | UUID | Yes | — | Unique identifier |
| `name` | string | No | **Yes** | Display name (max 255 chars) |
| `description` | string | No | No | Optional description |
| `currency` | string | No | No | ISO 4217 currency code (defaults to account currency) |
| `effective_start_date` | date (`YYYY-MM-DD`) | No | **Yes** | Start of validity period |
| `effective_end_date` | date (`YYYY-MM-DD`) | No | **Yes** | End of validity period |
| `enabled` | boolean | No | No | Whether the list can be attached to cost models (default: `true`) |
| `version` | integer | Yes | — | Auto-incremented on rate/date/currency changes |
| `rates` | array | No | No | List of rate objects (see [Rate Formats](#rate-formats)) |
| `created_timestamp` | datetime | Yes | — | ISO 8601 creation timestamp |
| `updated_timestamp` | datetime | Yes | — | ISO 8601 last-updated timestamp |

---

## Endpoints

### List `GET /api/cost-management/v1/price-lists/`

Returns a paginated list of price lists.

```bash
curl http://localhost:8000/api/cost-management/v1/price-lists/
```

**Response:**

```json
{
  "meta": { "count": 9, "limit": 10, "offset": 0 },
  "links": { "first": "...", "next": null, "previous": null, "last": "..." },
  "data": [
    {
      "uuid": "9770bc93-ef78-4681-b448-a35a460eea89",
      "name": "Production OCP Rates",
      "description": "Standard rates for production clusters",
      "currency": "USD",
      "effective_start_date": "2026-01-01",
      "effective_end_date": "2026-12-31",
      "enabled": true,
      "version": 1,
      "rates": [...],
      "created_timestamp": "2026-04-13T14:23:27.317050Z",
      "updated_timestamp": "2026-04-13T14:23:27.317057Z"
    }
  ]
}
```

---

### Create `POST /api/cost-management/v1/price-lists/`

Creates a new price list. Returns `201 Created` on success.

**Minimal example (tiered rate):**

```bash
curl -X POST http://localhost:8000/api/cost-management/v1/price-lists/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Price List",
    "currency": "USD",
    "effective_start_date": "2026-01-01",
    "effective_end_date": "2026-12-31",
    "rates": [
      {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "tiered_rates": [
          {"value": "1.50", "unit": "USD", "usage": {"usage_start": null, "usage_end": null}}
        ],
        "cost_type": "Infrastructure"
      }
    ]
  }'
```

**Response:**

```json
{
  "uuid": "a3356619-17be-41e2-bfbd-985dc95cbaa1",
  "name": "My Price List",
  "description": "",
  "currency": "USD",
  "effective_start_date": "2026-01-01",
  "effective_end_date": "2026-12-31",
  "enabled": true,
  "version": 1,
  "rates": [
    {
      "metric": {"name": "cpu_core_usage_per_hour"},
      "description": "",
      "rate_id": "f6c05b6a-50ae-40f0-955a-3e0a1e57a661",
      "custom_name": "cpu_core_usage_per_hour-Infrastructure",
      "tiered_rates": [
        {"value": 1.5, "usage": {"usage_start": null, "usage_end": null}, "unit": "USD"}
      ],
      "cost_type": "Infrastructure"
    }
  ],
  "created_timestamp": "2026-04-22T09:42:35.674430Z",
  "updated_timestamp": "2026-04-22T09:42:35.682611Z"
}
```

> **Note:** The response enriches each rate with `rate_id` and `custom_name` — these are
> backend-managed fields and do not need to be sent on create or update.

---

### Retrieve `GET /api/cost-management/v1/price-lists/{uuid}/`

Returns a single price list by UUID.

```bash
curl http://localhost:8000/api/cost-management/v1/price-lists/a3356619-17be-41e2-bfbd-985dc95cbaa1/
```

Returns `404 Not Found` if the UUID does not exist.

---

### Update `PUT /api/cost-management/v1/price-lists/{uuid}/`

Replaces the price list with the supplied body. Returns `200 OK` on success.

> ⚠️ `PATCH` is **not supported** — use `PUT` and include all fields you want to keep.

**Version increment rules:**
- `version` is **incremented** when `rates`, `effective_start_date`, `effective_end_date`, or `currency` change.
- `version` is **not incremented** for `name`, `description`, or `enabled` changes.

**Disabled price list restrictions:**
When `enabled` is `false`, only `name`, `description`, and `enabled` may be updated.
Attempting to change rates, dates, or currency on a disabled list returns `400 Bad Request`.

**Example — rename only (version stays at 1):**

```bash
curl -X PUT http://localhost:8000/api/cost-management/v1/price-lists/a3356619-17be-41e2-bfbd-985dc95cbaa1/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "currency": "USD",
    "effective_start_date": "2026-01-01",
    "effective_end_date": "2026-12-31"
  }'
```

**Example — update rates (version increments to 2):**

```bash
curl -X PUT http://localhost:8000/api/cost-management/v1/price-lists/a3356619-17be-41e2-bfbd-985dc95cbaa1/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "currency": "USD",
    "effective_start_date": "2026-01-01",
    "effective_end_date": "2026-12-31",
    "rates": [
      {
        "metric": {"name": "cpu_core_usage_per_hour"},
        "tiered_rates": [
          {"value": "3.00", "unit": "USD", "usage": {"usage_start": null, "usage_end": null}}
        ],
        "cost_type": "Infrastructure"
      }
    ]
  }'
```

> **Recalculation side-effect:** If `rates` or dates change and the price list covers the
> current month, cost recalculation is automatically triggered for all affected providers.

---

### Delete `DELETE /api/cost-management/v1/price-lists/{uuid}/`

Deletes a price list. Returns `204 No Content` on success.

**Constraint:** A price list **cannot be deleted** if it is currently assigned to one or more
cost models. The response will be `400 Bad Request`:

```json
{
  "errors": [
    {
      "detail": "Cannot delete price list 'My Price List': it is assigned to 1 cost model(s).",
      "source": "non_field_errors",
      "status": 400
    }
  ]
}
```

Remove the assignment from the cost model first, then retry the delete.

---

### Affected Cost Models `GET /api/cost-management/v1/price-lists/{uuid}/affected-cost-models/`

Returns the list of cost models that this price list is assigned to, along with priority.

```bash
curl http://localhost:8000/api/cost-management/v1/price-lists/a3356619-17be-41e2-bfbd-985dc95cbaa1/affected-cost-models/
```

**Response:**

```json
[
  {
    "uuid": "b2c3d4e5-...",
    "name": "Production Cost Model",
    "priority": 1
  }
]
```

Returns an empty list `[]` if not assigned to any cost model.

---

## Filtering

The list endpoint supports the following query parameters for filtering:

| Parameter | Type | Match | Example |
|---|---|---|---|
| `name` | string | Case-insensitive substring | `?name=production` |
| `uuid` | UUID | Exact match | `?uuid=9770bc93-ef78-4681-b448-a35a460eea89` |
| `enabled` | boolean | Exact match | `?enabled=true` or `?enabled=false` |

**Examples:**

```bash
# Find all price lists whose name contains "OCP"
curl "http://localhost:8000/api/cost-management/v1/price-lists/?name=OCP"

# Find only disabled price lists
curl "http://localhost:8000/api/cost-management/v1/price-lists/?enabled=false"

# Find a specific price list by UUID
curl "http://localhost:8000/api/cost-management/v1/price-lists/?uuid=9770bc93-ef78-4681-b448-a35a460eea89"
```

---

## Ordering

Use the `ordering` query parameter. Prefix with `-` for descending order.

| Value | Description |
|---|---|
| `name` | Sort alphabetically by name (default) |
| `-name` | Sort reverse alphabetically |
| `effective_start_date` | Sort by start date ascending |
| `-effective_start_date` | Sort by start date descending |
| `updated_timestamp` | Sort by last updated ascending |
| `-updated_timestamp` | Sort by last updated descending (most recent first) |

**Examples:**

```bash
# Most recently updated first
curl "http://localhost:8000/api/cost-management/v1/price-lists/?ordering=-updated_timestamp"

# Alphabetical by name
curl "http://localhost:8000/api/cost-management/v1/price-lists/?ordering=name"
```

---

## Pagination

Standard pagination via `limit` and `offset`:

| Parameter | Default | Description |
|---|---|---|
| `limit` | `10` | Number of results per page |
| `offset` | `0` | Number of results to skip |

```bash
# Page 2 with 5 results per page
curl "http://localhost:8000/api/cost-management/v1/price-lists/?limit=5&offset=5"
```

Filters and ordering can be combined with pagination:

```bash
curl "http://localhost:8000/api/cost-management/v1/price-lists/?name=production&ordering=-updated_timestamp&limit=10&offset=0"
```

---

## Rate Formats

Each rate in the `rates` array must include:

| Field | Required | Description |
|---|---|---|
| `metric.name` | Yes | One of the supported metric names (see below) |
| `cost_type` | Yes | `"Infrastructure"` or `"Supplementary"` |
| `tiered_rates` OR `tag_rates` | Yes | Exactly one of the two rate formats |
| `description` | No | Optional label |

### Tiered Rate

A flat rate applied to all usage (or within a usage band).

```json
{
  "metric": {"name": "cpu_core_usage_per_hour"},
  "tiered_rates": [
    {
      "value": "1.50",
      "unit": "USD",
      "usage": {
        "usage_start": null,
        "usage_end": null
      }
    }
  ],
  "cost_type": "Infrastructure"
}
```

For banded rates (e.g. first 100 hours at one rate, remainder at another), provide multiple
entries with `usage_start` / `usage_end` populated:

```json
{
  "metric": {"name": "cpu_core_usage_per_hour"},
  "tiered_rates": [
    {"value": "0.50", "unit": "USD", "usage": {"usage_start": null, "usage_end": 100}},
    {"value": "0.30", "unit": "USD", "usage": {"usage_start": 100, "usage_end": null}}
  ],
  "cost_type": "Supplementary"
}
```

### Tag Rate

A rate that varies by tag key/value on the resource. Requires a `default: true` entry.

```json
{
  "metric": {"name": "node_cost_per_month"},
  "tag_rates": {
    "tag_key": "instance-type",
    "tag_values": [
      {"unit": "USD", "value": "310.00", "default": false, "tag_value": "small", "description": "Small node"},
      {"unit": "USD", "value": "620.00", "default": false, "tag_value": "medium", "description": "Medium node"},
      {"unit": "USD", "value": "930.00", "default": true,  "tag_value": "large",  "description": "Large node (default)"}
    ]
  },
  "cost_type": "Infrastructure"
}
```

> **Constraint:** Only one unique `tag_key` per `metric`+`cost_type` combination is allowed
> within a single price list.

---

## Supported Metrics

These are the valid values for `metric.name`:

| Metric name | Unit | Notes |
|---|---|---|
| `cpu_core_usage_per_hour` | core·hour | CPU core actual usage |
| `cpu_core_request_per_hour` | core·hour | CPU core requested |
| `cpu_core_effective_usage_per_hour` | core·hour | Effective (capped) usage |
| `memory_gb_usage_per_hour` | GB·hour | Memory actual usage |
| `memory_gb_request_per_hour` | GB·hour | Memory requested |
| `memory_gb_effective_usage_per_hour` | GB·hour | Effective (capped) usage |
| `storage_gb_usage_per_month` | GB·month | PVC storage actual usage |
| `storage_gb_request_per_month` | GB·month | PVC storage requested |
| `node_cost_per_month` | node·month | Per-node flat cost |
| `cluster_cost_per_month` | cluster·month | Per-cluster flat cost |
| `cluster_cost_per_hour` | cluster·hour | Per-cluster hourly cost |
| `pvc_cost_per_month` | PVC·month | Per-PVC flat cost |
| `project_per_month` | project·month | Tag-only metric |
| `vm_cost_per_month` | VM·month | Per-VM flat cost |
| `vm_cost_per_hour` | VM·hour | Per-VM hourly cost |
| `gpu_cost_per_month` | GPU·month | Per-GPU flat cost |

> `project_per_month` only supports `tag_rates`, not `tiered_rates`.

---

## Versioning Behavior

The `version` field tracks meaningful semantic changes to a price list:

| Change | Version increments? |
|---|---|
| `rates` changed | Yes |
| `effective_start_date` or `effective_end_date` changed | Yes |
| `currency` changed | Yes |
| `name` changed | No |
| `description` changed | No |
| `enabled` toggled | No |

When version increments and the price list covers the current month, cost recalculation
is automatically triggered for all providers assigned to cost models that use this price list.

---

## Known Limitations

- **`PATCH` is not supported.** Use `PUT` with the full body.
- **Disabled price lists** cannot be attached to cost models. They still participate in cost
  calculation if they were already assigned and their validity period covers the billing date.
- **Sort and filter** do not apply inside the `rates` array — filtering is only on top-level
  price list fields.
- **Assigned cost models** are not inline in the list/retrieve responses. Use the
  [`/affected-cost-models/`](#affected-cost-models-get-apicost-managementv1price-listsuuidaffected-cost-models)
  sub-endpoint to check assignments.

---

## Validation Errors

All validation errors follow the standard error envelope:

```json
{
  "errors": [
    {
      "detail": "effective_end_date must be on or after effective_start_date.",
      "source": "non_field_errors",
      "status": 400
    }
  ]
}
```

Common error cases:

| Scenario | Status |
|---|---|
| Missing `name` | `400` |
| `effective_end_date` before `effective_start_date` | `400` |
| `currency` mismatch when attaching to a cost model | `400` |
| Attaching a disabled price list to a cost model | `400` |
| Updating rates/dates/currency on a disabled price list | `400` |
| Deleting a price list assigned to a cost model | `400` |
| UUID not found | `404` |
