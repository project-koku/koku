# Current Architecture — Cost Models

**Parent**: [README.md](README.md) · **Status**: Due Diligence

---

## 1. Data Model

### 1.1 `CostModel` (`cost_model`)

The central entity. Stores rates as JSON, markup, distribution config,
and currency. Has no foreign keys to providers — assignment is via
`CostModelMap`.

| Field | Type | Notes |
|-------|------|-------|
| `uuid` | `UUIDField` PK | Default `uuid4` |
| `name` | `TextField` | Indexed |
| `description` | `TextField` | |
| `source_type` | `CharField(50)` | `Provider.PROVIDER_CHOICES` (OCP, AWS, Azure, GCP, etc.) |
| `rates` | `JSONField` | Canonical rate definitions (tiered + tag) |
| `markup` | `JSONField` | |
| `distribution` | `TextField` | `cpu` or `memory` |
| `distribution_info` | `JSONField` | Platform/worker/GPU/storage/network flags |
| `currency` | `TextField` | |
| `created_timestamp` | `DateTimeField` | auto |
| `updated_timestamp` | `DateTimeField` | auto |

### 1.2 `CostModelMap` (`cost_model_map`)

The **assignment table** — links a cost model to a provider (OCP cluster).

| Field | Type | Notes |
|-------|------|-------|
| `id` | Auto PK | |
| `provider_uuid` | `UUIDField` | **Not** a Django FK to `Provider` — stored by value |
| `cost_model` | `ForeignKey` → `CostModel` | `on_delete=CASCADE` |

**Constraints**: `unique_together = ("provider_uuid", "cost_model")`

**Critical finding for COST-3920**: The DB constraint allows a provider
to appear in multiple rows with **different** cost models. However,
`CostModelManager.update_provider_uuids()` explicitly **rejects** any
provider that already has a `CostModelMap` row when assigning to a
new cost model. This one-model-per-provider invariant is
**application-level only**.

This means:
- The schema already supports multiple assignments per provider
- Adding a `context` column and relaxing the manager check to enforce
  `unique_together = ("provider_uuid", "context")` is structurally
  feasible without breaking the existing constraint

### 1.3 `PriceList` (`price_list`)

Versioned container for rates with effective dates. Linked to
`CostModel` via `PriceListCostModelMap`.

| Field | Type | Notes |
|-------|------|-------|
| `uuid` | UUIDField PK | |
| `name`, `description` | TextField | |
| `currency` | TextField | |
| `effective_start_date`, `effective_end_date` | DateField | |
| `enabled` | BooleanField | Default `True` |
| `version` | PositiveIntegerField | Default `1` |
| `rates` | JSONField | Mirror of CostModel.rates after sync |

### 1.4 `PriceListCostModelMap` (`price_list_cost_model_map`)

| Field | Type |
|-------|------|
| `price_list` | FK → PriceList |
| `cost_model` | FK → CostModel |
| `priority` | PositiveIntegerField |

**Constraint**: `unique_together = ("price_list", "cost_model")`,
ordered by `priority`.

### 1.5 `Rate` (`cost_model_rate`)

Normalized rate rows, FK to PriceList.

| Field | Type |
|-------|------|
| `uuid` | UUIDField PK |
| `price_list` | FK → PriceList |
| `custom_name` | CharField(50) |
| `metric`, `metric_type`, `cost_type` | CharField |
| `default_rate` | DecimalField |
| `tag_key` | CharField |
| `tag_values` | JSONField |

**Constraint**: `unique_together = ("price_list", "custom_name")`

### 1.6 `CostModelAudit` (`cost_model_audit`)

Trigger-populated audit table. Captures INSERT/UPDATE/DELETE on
`cost_model` with snapshot of all fields plus `provider_uuids` array
from `cost_model_map`.

### 1.7 `Provider` (`api_provider`)

OCP clusters are represented as `Provider` rows with `type = "OCP"`.
The `Provider.uuid` is what `CostModelMap.provider_uuid` references.

Key fields: `uuid` (PK), `name`, `type`, `authentication` (contains
`credentials.cluster_id`), `active`, `paused`, `customer` (FK),
`data_updated_timestamp`.

---

## 2. Cost Model Manager

`CostModelManager` (`cost_models/cost_model_manager.py`) orchestrates
CRUD and provider assignment.

### 2.1 Create flow

1. Deep-copy data, pop `provider_uuids`
2. `CostModel.objects.create(**cost_model_data)`
3. `update_provider_uuids(provider_uuids)` — creates `CostModelMap` rows
4. If rates exist: `_get_or_create_price_list()` + `_sync_rate_table()`

### 2.2 Provider assignment (`update_provider_uuids`)

**One-model-per-provider enforcement**:
```
For each new provider_uuid:
    existing = CostModelMap.objects.filter(provider_uuid=uuid)
    if existing.exists():
        raise CostModelException("already associated")
```

This is the **only** barrier to multiple cost models per provider.
For COST-3920, this check would change to:
```
existing = CostModelMap.objects.filter(provider_uuid=uuid, context=context)
```

### 2.3 Update flow

1. Update scalar/JSON fields on CostModel
2. If `rates` in payload: sync Rate rows via `_sync_rate_table()`
3. Queue `update_cost_model_costs` Celery task for affected providers

---

## 3. Cost Calculation Pipeline

### 3.1 Entry point

`update_cost_model_costs` Celery task receives `(schema, provider_uuid,
start_date, end_date)`. Always runs for OCP providers (even without a
cost model — distribution still happens).

### 3.2 Cost model resolution

`CostModelDBAccessor` opens tenant schema and resolves the cost model:
```python
CostModel.objects.filter(
    costmodelmap__provider_uuid=self.provider_uuid
).first()
```

**Single-model assumption**: `.first()` returns one cost model.
For COST-3920, this must become context-aware — either:
- Run the pipeline once per context (N cost models × 1 provider)
- Pass context as a parameter to the accessor

### 3.3 OCP cost updater steps

`OCPCostModelCostUpdater.update_summary_cost_model_costs()`:

1. `_update_usage_costs` — tiered rates → `usage_costs.sql`
2. `_update_markup_cost` — markup percentage
3. `_update_monthly_cost` — node/cluster/PVC monthly rates
4. Tag-based rates (if configured)
5. `distribute_costs_and_update_ui_summary` — platform/worker/GPU
   distribution → UI summary table refresh

### 3.4 SQL execution

SQL files are under `koku/masu/database/sql/openshift/cost_model/`.
Key pattern:
- **DELETE** existing cost rows for (source_uuid, dates, cost_model_rate_type)
- **INSERT** new cost rows computed from rates × usage

Rates are **bound as template parameters** in Python, not joined from
`cost_model_map` in SQL. The SQL uses `{{source_uuid}}` and
`{{report_period_id}}` for scoping.

### 3.5 Implications for COST-3920

The DELETE → INSERT pattern means the pipeline can run per-context
if each context's rows are distinguishable. A `context` column (or
equivalent discriminator) on `reporting_ocpusagelineitem_daily_summary`
would allow:
- DELETE WHERE source_uuid = X AND context = 'Provider'
- INSERT ... with context = 'Provider'

Without this, running the pipeline for context B would overwrite
context A's data.

---

## 4. Reporting Tables

### 4.1 Daily summary (fact table)

`reporting_ocpusagelineitem_daily_summary` — the central OCP fact table.
Contains both usage quantities and computed cost columns:

- Usage: `pod_usage_cpu_core_hours`, `pod_usage_memory_gigabyte_hours`, etc.
- Costs: `cost_model_cpu_cost`, `cost_model_memory_cost`,
  `cost_model_volume_cost`, `cost_model_gpu_cost`
- Metadata: `cost_model_rate_type` (Infrastructure, Supplementary,
  platform_distributed, worker_distributed, etc.)
- Distribution: `distributed_cost`

**No context column exists today.**

### 4.2 UI summary tables

Partitioned rollup tables (`reporting_ocp_*_summary_p`) are populated
from the daily summary via SQL in
`koku/masu/database/sql/openshift/ui_summary/`.

These aggregate by day, cluster, and `cost_model_rate_type` — but
not by context.

### 4.3 Data volume implications

With 3 contexts, each cluster's cost data triples in the daily
summary and UI summary tables. For a tenant with 50 clusters and
3 contexts, this is 150× the per-cluster cost rows instead of 50×.

---

## 5. API Layer

### 5.1 Cost model CRUD

`CostModelViewSet` at `/api/v1/cost-models/`:
- `GET` (list/retrieve), `POST`, `PUT`, `DELETE`
- Filtered by RBAC `cost_model.read` / `cost_model.write`
- `source_uuids` field controls `CostModelMap` assignment

### 5.2 OCP report endpoints

| Path | View | Report Type |
|------|------|-------------|
| `reports/openshift/costs/` | `OCPCostView` | `costs` |
| `reports/openshift/compute/` | `OCPCpuView` | `cpu` |
| `reports/openshift/memory/` | `OCPMemoryView` | `memory` |
| `reports/openshift/volumes/` | `OCPVolumeView` | `volume` |
| `reports/openshift/network/` | `OCPNetworkView` | `network` |
| `reports/openshift/gpu/` | `OCPGpuView` | `gpu` |

**No `cost_model_context` query parameter exists.**

### 5.3 AWS `cost_type` pattern (reference for implementation)

AWS has a `cost_type` query parameter that switches between
blended/unblended/amortized costs. The plumbing:

1. **Serializer** declares optional `cost_type` field
2. **`validate()`** defaults to user preference or system default
3. **QueryHandler** passes `cost_type` to ProviderMap constructor
4. **ProviderMap** uses `F(self.cost_type)` in ORM aggregates

This pattern is directly applicable to `cost_model_context` on OCP.

---

## 6. RBAC

### 6.1 Current architecture

- `IdentityHeaderMiddleware` calls RBAC service HTTP endpoint
- Response ACLs parsed into `user.access = {resource_type: {read: [...], write: [...]}}`
- `CostModelsAccessPermission` checks `user.access["cost_model"]`
- View `get_queryset()` filters by `cost_model.read` UUID list

### 6.2 Limitations for COST-3920

1. **No group-level properties** — Koku receives flat ACLs, not group
   objects. "Context" as a group property requires RBAC service changes.

2. **`attributeFilter.key` is ignored** — the ACL parser only uses
   `operation` and `value`. Multiple dimensions (UUID + context)
   cannot be distinguished.

3. **Cross-service dependency** — adding a "cost model context"
   dimension requires RBAC service team buy-in (new permission
   definitions, new resource attribute).

### 6.3 Alternatives

| Option | Approach | Pros | Cons |
|--------|----------|------|------|
| A | RBAC service adds `cost_model_context` resource type | Clean separation; RBAC audit trail | Cross-team dependency; timeline risk |
| B | Koku-side authorization for contexts | No external dependency; ships independently | Duplicates auth logic; no RBAC audit trail |
| C | Hybrid: Koku manages context visibility, RBAC manages cost model access | Pragmatic; no cross-service blocker | Context auth is weaker (no RBAC audit trail) |

**Recommendation**: Option C for v1 implementation, with a migration
path to Option A once the RBAC service supports `cost_model_context`
as a resource type. Design the API so the authorization backend is
an internal implementation detail — switching from Koku-side to
platform RBAC requires no API changes.

---

## 7. Entity Relationship (Current)

```
Provider (api_provider)
    │
    │ provider_uuid (by value)
    ▼
CostModelMap (cost_model_map)
    │
    │ cost_model_id (FK)
    ▼
CostModel (cost_model)
    │
    │ (reverse FK via PriceListCostModelMap)
    ▼
PriceListCostModelMap ──► PriceList (price_list)
                              │
                              │ (reverse FK)
                              ▼
                          Rate (cost_model_rate)
```

### Proposed additions for COST-3920

```
CostModelContext (NEW — tenant-scoped)
    │
    │ context_id (FK on CostModelMap)
    ▼
CostModelMap + context column
    │
    │ unique_together = (provider_uuid, context)
    ▼
[pipeline runs per context]
    │
    ▼
reporting_ocpusagelineitem_daily_summary + context column
    │
    ▼
reporting_ocp_*_summary_p + context column
```
