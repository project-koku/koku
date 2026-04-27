# Price Lists — API and Configuration Lifecycle

REST surface, tenant rules, attachment to cost models, and triggers that
enqueue pipeline work. Implementation links use paths from the repository
root `koku/`.

---

## Base URL

Cost model and price list routes are registered under the API v1 prefix
(see [`koku/koku/urls.py`](../../../koku/koku/urls.py) including
[`cost_models.urls`](../../../koku/cost_models/urls.py)):

- `.../v1/price-lists/`
- `.../v1/cost-models/`

Exact prefix depends on deployment (`API_PATH_PREFIX`).

---

## Price list REST lifecycle

[`PriceListViewSet`](../../../koku/cost_models/price_list_view.py) (`basename="price-lists"`):

| Action | HTTP | Notes |
|--------|------|--------|
| List | `GET` | Query contract below; uses [`PriceListFilter`](../../../koku/cost_models/price_list_view.py) + [`SettingsFilter`](../../../koku/api/settings/utils.py) (same bracket style as Settings APIs). |
| Retrieve | `GET` | Single object by `{uuid}`. |
| Create | `POST` | Body validated by [`PriceListSerializer`](../../../koku/cost_models/price_list_serializer.py). |
| Full update | `PUT` | Delegates to serializer `update` → [`PriceListManager.update`](../../../koku/cost_models/price_list_manager.py). |
| Delete | `DELETE` | [`perform_destroy`](../../../koku/cost_models/price_list_view.py) uses manager: **blocked** if any `PriceListCostModelMap` exists. |
| Duplicate | `POST .../price-lists/{uuid}/duplicate/` | Copies rates, dates, currency, description; new name `Copy of …` (max 255 chars); `version=1`, `enabled=true`; **no** cost-model attachments. See [`duplicate`](../../../koku/cost_models/price_list_view.py). |
| Affected cost models | `GET .../price-lists/{uuid}/affected-cost-models/` | Same assignment info as `assigned_cost_models` on the main resource, as a dedicated array endpoint. |

**List query parameters** (enforced in [`PriceListFilter.filter_queryset`](../../../koku/cost_models/price_list_view.py)): only **`offset`**, **`limit`**, **`filter`**, and **`order_by`** are accepted at the top level. Anything else → **400** (`Unsupported parameter or invalid value`).

**`filter[field]=value`** — allowed keys:

| Key | Behavior |
|-----|----------|
| `name` | Case-insensitive **substring**; comma-separated values are **AND**ed (each substring must match). |
| `uuid` | Exact UUID. |
| `enabled` | Boolean. |
| `currency` | Exact match, case-insensitive. |

Unknown `filter[...]` keys → **400**.

**`order_by[field]=asc|desc`** — `field` must resolve to a column or annotation on the list queryset (e.g. `name`, `effective_start_date`, `effective_end_date`, `updated_timestamp`, `currency`, **`assigned_cost_model_count`**). Invalid field or direction → **400**. Default ordering is **`name`** ascending (see `PriceListFilter.Meta.default_ordering`).

**Response shape** ([`PriceListSerializer.to_representation`](../../../koku/cost_models/price_list_serializer.py)): besides persisted fields, each price list includes read-only **`assigned_cost_model_count`** and **`assigned_cost_models`** (`{uuid, name, priority}` per map), so clients do not need a second request to see assignments (the `affected-cost-models` route remains for callers that only need that slice).

**Permissions**: [`CostModelsAccessPermission`](../../../koku/api/common/permissions/cost_models_access.py) on the viewset.

**Caching**: list/create/retrieve/update/destroy, `affected-cost-models`, and `duplicate` are wrapped with `@never_cache`.

---

## Update rules and versioning

[`PriceListManager.update`](../../../koku/cost_models/price_list_manager.py):

- **Disabled lists**: only `name`, `description`, `enabled` may change;
  other fields raise `PriceListException`.
- **`version`**: incremented when `rates`, validity dates, or `currency`
  change — not for name/description/enabled alone.
- **Recalculation**: when `rates` or validity dates change, `_trigger_recalculation`
  enqueues [`update_cost_model_costs`](../../../koku/masu/processor/tasks.py) for
  **each active provider** mapped to any cost model linked to this price list,
  for the **current month to today** window — only if the list’s validity
  intersects the current month.
- **Rate enrichment**: `sync_rate_table` enriches the `rates` JSON in-place
  with `rate_id` (UUID of the `Rate` row) and `custom_name` (stable slug)
  after every create/update. These are saved back to `PriceList.rates`, so
  GET responses include them. API clients should treat them as **read-only**;
  if sent back on a PUT, they are used to identify existing rows but must not
  be invented. See [`rate_sync.py`](../../../koku/cost_models/rate_sync.py).

---

## Cost model ↔ price list attachment

[`CostModelSerializer`](../../../koku/cost_models/serializers.py) exposes:

- **Write**: optional `price_list_uuids` — ordered list; position `i` maps
  to `priority = i + 1` in
  [`attach_price_lists_to_cost_model`](../../../koku/cost_models/price_list_manager.py).
- **Read**: `price_lists` array of `{uuid, name, priority}` from
  `cost_model.price_list_maps`.

On **create**, after [`CostModelManager.create`](../../../koku/cost_models/cost_model_manager.py),
if `price_list_uuids` was sent, attachments are applied in the same request.

On **update**, if `price_list_uuids` is present (including `[]`), **all**
existing maps for that cost model are replaced.

**Validation** (manager): every UUID must exist; each list must be **enabled**;
**currency** must match the cost model.

---

## Cost model rates and dual-write

This section is the **implementation** of the transitional **dual-write**
strategy described in [README.md § Dual-write transition](./README.md#dual-write-transition-product-plan).

[`CostModelManager`](../../../koku/cost_models/cost_model_manager.py):

- **Create**: if the new cost model has non-empty `rates`, `_get_or_create_price_list`
  ensures a default `PriceList` + map (priority 1) exists, copying rates.
- **Update**: when the payload includes `rates`, the linked price list (first
  by priority) is updated in lockstep with `CostModel.rates`.

So every cost-model–driven change to `rates` is **also** written to the
primary attached `PriceList`, keeping the cost model UI and date-based
pipeline aligned until the price list UI exists and **`CostModel.rates`**
can be retired.

**Auto-created price list date window**: when `_get_or_create_price_list`
creates a new list, it uses a hardcoded
`effective_start_date=date(2026, 3, 1)` and
`effective_end_date=date(2099, 12, 31)`. This open-ended window ensures the
auto-created list always covers the current month. It is tech debt to be
revisited when the price list UI lets users manage validity windows directly.

---

## Other pipeline triggers

Changing **providers** on a cost model still dispatches
`update_cost_model_costs` per affected provider (existing behavior in
`CostModelManager.update_provider_uuids` / update flows — see
[`cost_model_manager.py`](../../../koku/cost_models/cost_model_manager.py)).

Price list **PUT** adds an additional path: recalculation keyed off the
**price list’s** maps and date intersection, as described above.

---

## Tenant scope

`PriceList`, `PriceListCostModelMap`, and `CostModel` live in the **tenant**
schema (`cost_models` app). API handlers run in tenant context like other
cost model endpoints — same multi-tenancy rules as the rest of Koku; see
[AGENTS.md](../../../AGENTS.md) (schema-per-tenant).
