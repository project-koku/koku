# COST-575: Lifecycle of Price Lists — Implementation Progress

## PRD Reference
`~/Downloads/PRD07 COST-575 Lifecycle of Price Lists (1).pdf`

## Scope
Phase 1 only: decouple price lists from cost models, add validity periods, versioning, multiple price lists per cost model with priority ordering. Current-month recalculation behavior unchanged from today.

## Step 1: Models + Migration + Tests (DONE)

**New models** in `koku/cost_models/models.py`:
- **`PriceList`** — standalone entity with uuid, name, description, currency, effective_start_date, effective_end_date, enabled, version, rates, timestamps
- **`PriceListCostModelMap`** — links price lists to cost models with priority (unique on price_list+cost_model)

**Migration**: `0010_add_price_list_models.py` — creates both tables in tenant schemas

**Tests**: `koku/cost_models/test/test_price_list_models.py` — 11 tests, all passing

## Step 2: Price List Manager (DONE)

**File**: `koku/cost_models/price_list_manager.py`
- `PriceListManager.__init__(price_list_uuid=None)` — loads existing PriceList
- `create(**data)` — creates PriceList
- `update(**data)` — updates fields; increments version if rates change; enforces disabled restrictions
- `delete()` — deletes only if not assigned to any cost model
- `attach_price_lists_to_cost_model(cost_model_uuid, price_list_uuids)` — replaces all mappings with new ordered list
- `get_cost_model_price_lists(cost_model_uuid)` — returns attached PLs ordered by priority
- `get_effective_price_list(cost_model_uuid, target_date)` — priority resolution for a given date

**Tests**: `koku/cost_models/test/test_price_list_manager.py` — 24 tests, all passing

## Step 3: API Endpoints (DONE)

**Files**:
- `koku/cost_models/price_list_serializer.py` — PriceListSerializer with date validation, delegates to PriceListManager
- `koku/cost_models/price_list_view.py` — PriceListViewSet with full CRUD, filtering (name, uuid, enabled)
- `koku/cost_models/urls.py` — registered `price-lists` route

**Endpoints**:
- `GET /api/v1/price-lists/` — list with filtering
- `POST /api/v1/price-lists/` — create
- `GET /api/v1/price-lists/{uuid}/` — retrieve
- `PUT /api/v1/price-lists/{uuid}/` — update
- `DELETE /api/v1/price-lists/{uuid}/` — delete (blocked if assigned to cost model)

**Tests**: `koku/cost_models/test/test_price_list_view.py` — 11 tests, all passing
- Note: view tests require `ENHANCED_ORG_ADMIN=True` (no RBAC service in test env)

## Step 4: Data Migration (DONE)

**Migration**: `0011_migrate_cost_model_rates_to_price_lists.py`
- For each CostModel with rates: creates PriceList "{name} prices", copies rates+currency
- Validity: 2026-03-01 → 2099-12-31
- Links to cost model with priority 1
- Reversible: deletes auto-migrated price lists

**Tests**: `koku/cost_models/test/test_price_list_migration.py` — 2 tests, all passing

## Total: 57 tests, all passing

## Step 5: Rate resolution via price lists (DONE)

**File**: `koku/masu/database/cost_model_db_accessor.py`

Changed `CostModelDBAccessor` to resolve rates via price lists:
- New `effective_rates` property replaces direct `CostModel.rates` access
- When `target_date` is provided, calls `get_effective_price_list(cost_model_uuid, target_date)`
- If a price list is returned, uses its rates; if None, returns empty rates (zero costs per PRD)
- When `target_date` is None, falls back to `CostModel.rates` for backward compatibility
- All downstream properties (`price_list`, `infrastructure_rates`, `supplementary_rates`,
  `tag_based_price_list`, etc.) now use `effective_rates` instead of `CostModel.rates`

**Tests**: `koku/masu/test/database/test_cost_model_db_accessor.py` — new test class `CostModelDBAccessorTagRatesPriceListTest`

## Step 6: Recalculation trigger on rate/date changes (DONE)

**File**: `koku/cost_models/price_list_manager.py` — `_trigger_recalculation()`

- Triggered from `PriceListManager.update()` when rates or validity dates change
- Finds all cost models linked to the price list via `PriceListCostModelMap`
- Finds all providers linked to those cost models via `CostModelMap`
- Dispatches `update_cost_model_costs` Celery task for each active provider
- Only triggers if the price list covers the current month

## Step 7: Disabled price lists behavior (DONE — PRD updated)

Per updated PRD:
- **Disabled price lists still participate in calculation** — `get_effective_price_list()` does
  NOT filter by `enabled`. The `enabled` flag only controls whether a list can be newly attached.
- **Disable/enable does NOT trigger recalculation** — toggling status has no effect on costs.
- **Disabled lists cannot be newly attached** to a cost model (enforced in `attach_price_lists_to_cost_model`)

## Step 8: Version increment rules (DONE — PRD clarified)

Version increments on: **rates**, **validity period** (`effective_start_date`/`effective_end_date`), **currency** changes.

Version does NOT increment on: **name**, **description**, **status** (enabled/disabled) changes.

## Step 9: Cost model API integration (DONE)

**File**: `koku/cost_models/serializers.py` — `CostModelSerializer` updated

- `GET /cost-models/{uuid}/` now returns `price_lists` array with uuid, name, priority (ordered by priority)
- `POST /cost-models/` accepts optional `price_list_uuids` to attach price lists on create
- `PUT /cost-models/{uuid}/` accepts optional `price_list_uuids` to replace attached price lists on update
- Follows the same pattern as `sources`/`source_uuids` enrichment already in the serializer

## Step 10: Affected cost models endpoint (DONE)

PRD Phase 1 item 4: when saving price list changes, show which cost models are affected.
The UI calls this BEFORE saving to show "this change affects cost models X, Y, Z — do you want to continue?"

**Endpoint**: `GET /api/v1/price-lists/{uuid}/affected-cost-models/`
- Returns list of cost models linked to this price list with their UUIDs, names, and priorities
- Implemented as a DRF `@action` on `PriceListViewSet`
- No date logic — just queries `PriceListCostModelMap`

**Tests**: 2 new tests in `test_price_list_view.py` (total 13 view tests)

## Key Design Decisions
- **No changes to CostModel**: existing `rates` and `currency` fields stay untouched for backward compatibility
- **Tenant-scoped**: `cost_models` is in `TENANT_APPS`, so all new tables live in tenant schemas alongside cost_model tables
- **Priority is on the mapping, not the price list**: a price list can have different priorities in different cost models (per PRD)
- **Old clients keep working**: if a cost model has no price lists attached, it uses legacy `rates` on the cost model
- **Same permission class**: PriceListViewSet uses CostModelsAccessPermission for consistent RBAC

## Dev Environment
- Clone: `/home/ydayagi/repos/upstream/koku-price-lists`
- Branch: `cost575`
- Test DB: `docker compose -f docker-compose.test.yml` — postgres:16 on port **15433** (separate from main koku on 15432)
- Run all tests:
  ```
  cd /home/ydayagi/repos/upstream/koku-price-lists && \
    PROMETHEUS_MULTIPROC_DIR=/tmp \
    DJANGO_READ_DOT_ENV_FILE=False \
    DATABASE_SERVICE_NAME=POSTGRES_SQL \
    DATABASE_ENGINE=postgresql \
    DATABASE_NAME=postgres \
    POSTGRES_SQL_SERVICE_HOST=localhost \
    POSTGRES_SQL_SERVICE_PORT=15433 \
    DATABASE_USER=postgres \
    DATABASE_PASSWORD=postgres \
    DATABASE_ADMIN=postgres \
    DISABLE_UNLEASH=True \
    ENHANCED_ORG_ADMIN=True \
    KEEPDB=True \
    PYTHONPATH="/home/ydayagi/repos/upstream/koku-price-lists:/home/ydayagi/repos/upstream/koku-price-lists/koku" \
    /home/ydayagi/.local/share/virtualenvs/koku-amFGuhP0/bin/python koku/manage.py test \
    cost_models.test.test_price_list_models \
    cost_models.test.test_price_list_manager \
    cost_models.test.test_price_list_view \
    cost_models.test.test_price_list_migration \
    -v 2
  ```
  Note: first run requires `KEEPDB=False` to create the test DB and load fixtures.
