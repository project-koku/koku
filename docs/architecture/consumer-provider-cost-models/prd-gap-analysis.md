# PRD Gap Analysis — COST-3920

**Parent**: [README.md](README.md) · **Status**: Design Proposal

Section-by-section analysis of each PRD requirement against the
current codebase, with proposed implementation and code sketches.

---

## GA-1: Cost Model Context Entity

**PRD**: Administrators create a list of cost model contexts (max 3,
one designated default). Stored at the organization/tenant level.

**Current state**: No `CostModelContext` model exists.

**Proposed implementation**:
```python
class CostModelContext(models.Model):
    class Meta:
        db_table = "cost_model_context"
        unique_together = ("name",)  # per tenant schema

    uuid = models.UUIDField(primary_key=True, default=uuid4)
    name = models.CharField(max_length=50)
    display_name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    position = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    data_visibility = models.CharField(
        max_length=20,
        choices=DataVisibility.choices,
        default=DataVisibility.CLOUD_AND_OCP,
    )
    created_timestamp = models.DateTimeField(auto_now_add=True)
```

Where `DataVisibility` is:
```python
class DataVisibility(models.TextChoices):
    OCP_ONLY = "ocp_only", "OpenShift only"
    CLOUD_AND_OCP = "cloud_and_ocp", "Cloud + OpenShift"
```

**Constraints**:
- Exactly one row with `is_default=True` per tenant schema (partial unique index)
- Max 3 rows per tenant schema (serializer + `position` CHECK constraint)
- Default context cannot be deleted (viewset guard)
- `data_visibility` defaults to `cloud_and_ocp` (backward-compatible)

**CRUD API**: `CostModelContextSerializer` (ModelSerializer) +
`CostModelContextViewSet` (ModelViewSet) at `/api/v1/cost-model-contexts/`.
Supports GET, POST, PUT, DELETE.

**Risk**: [R15](./risk-register.md#r15-max-3-contexts--no-db-enforcement),
[R16](./risk-register.md#r16-default-context-cannot-be-deleted),
[R13](./risk-register.md#r13-was-tq-2-ocp-on-cloud-context-interaction--reopened)

---

## GA-2: RBAC Integration

**PRD**: Groups see only permitted contexts.

**Current state**: Koku's RBAC service has no "context" dimension.
`CostModelsAccessPermission` checks `cost_model.read/write` only.

**Proposed implementation (v1 — Koku-side authorization)**:

Kessel/ReBAC is out of scope for v1 per project decision. We propose
a `CostModelContextPermission` class:

```python
class CostModelContextPermission(CostModelsAccessPermission):
    def has_permission(self, request, view):
        if "cost_model_context" not in request.query_params:
            return True  # standard OCP report permissions apply

        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return True

        # Check cost_model.read access
        access = request.user.access or {}
        cost_model_access = access.get("cost_model", {})
        read_list = cost_model_access.get("read", [])
        return bool(read_list)
```

When `cost_model_context` is not in query params, the permission
passes through — existing OCP report behavior is unchanged (backward
compatible). When explicitly requested, the user must have
`cost_model.read` access.

**Migration path**: When platform RBAC adds `cost_model_context` as
a resource type, replace the Koku-side check with the RBAC lookup.
The API contract does not change.

**PRD extended RBAC examples** (added 2026-05-05):

- User has access to Cluster 1 and the default context → sees
  default context costs for Cluster 1 (or just usage if no cost
  model assigned to default on that cluster).
- User has access to Cluster 1 and Context B, but NOT the default
  context → sees only Context B for Cluster 1; default is hidden.
- User has access to Context B and default context, plus Cluster 1
  and Cluster 2 → sees both contexts on both clusters.

Context access is **additive to cluster access**, not a replacement.
Having access to a context does not grant access to all clusters
with that context — cluster RBAC still applies.

**Alternatives evaluated**: See [current-architecture.md § 6.3](./current-architecture.md#63-alternatives)

**Risk**: [R3](./risk-register.md#r3-was-tq-5-rbac-context-authorization--resolved-by-precedent)

---

## GA-3: Cost Model Creation

**PRD**: Cost model creation is unchanged (context-free).

**Current state**: Already works. Cost models exist independently
of contexts. Assignment to contexts happens via `CostModelMap`.

**No work needed.**

---

## GA-4: Assignment with Context

**PRD**: One cost model per context per OCP cluster. Assignment
goes through `CostModelMap`. Each context exists for each cluster
(contexts are org-level entities with per-cluster "slots").
Context assignment also declares data visibility (OpenShift-only
vs cloud + OpenShift).

**Current state**: `CostModelMap` has `(provider_uuid, cost_model)`.
The manager enforces one-model-per-provider at the application level.

**Proposed implementation**:

1. Add FK `cost_model_context` on `CostModelMap` → `CostModelContext`
2. Change unique constraint to `unique_together = ("provider_uuid", "cost_model_context")`
3. Update `CostModelManager.update_provider_uuids()` to check per-context uniqueness
4. `CostModelContext.data_visibility` controls what cost data is
   visible when querying that context (see GA-11)

**Migration strategy (M1-M4)**:

| Migration | Type | Description |
|-----------|------|-------------|
| M1 | DDL | Create `CostModelContext` model (includes `data_visibility` field) |
| M2 | DDL | Add nullable `cost_model_context` FK to `CostModelMap` |
| M3 | DDL | Add unique constraint `(provider_uuid, cost_model_context)` |
| M4 | Data | Create default "Default context" context per tenant (renamable); assign all existing `CostModelMap` rows to it; set `data_visibility = 'cloud_and_ocp'` |

M4 uses `RunPython` with fail-fast on duplicate `(provider_uuid)`
rows — if a provider has multiple `CostModelMap` rows, the migration
raises an error with actionable guidance. This follows koku's norm
of non-destructive, deterministic data migrations.

**Note**: The updated PRD (2026-05-05) changed the default context
display name from "Consumer" to "Default context" and added the
requirement that the default context display name is renamable by
customers.

**Risk**: [R9](./risk-register.md#r9-update_provider_uuids-blocks-multi-assignment),
[R10](./risk-register.md#r10-was-tq-4-predecessor-pr-sequencing--resolved)

---

## GA-5: Default Metering

**PRD**: A context with no cost model still reports usage at $0.

**Current state**: Already works. When `CostModelDBAccessor` finds
no cost model, the pipeline returns empty rates. Usage data comes
from ingestion (context-independent). Distribution and UI summary
refresh still run.

**No work needed** beyond verifying with a test case.

**Risk**: [R17](./risk-register.md#r17-empty-context-shows-metering-at-0)

---

## GA-6: API `cost_model_context` Query Parameter

**PRD**: OCP report endpoints accept `cost_model_context` parameter.

**Current state**: No such parameter exists. AWS `cost_type` provides
the pattern to follow.

**Proposed implementation**:

1. **Serializer**: Add optional `cost_model_context` field to
   `OCPQueryParamSerializer`
2. **QueryParameters**: Add `cost_model_context` property; returns
   `None` when not explicitly provided (backward compatible)
3. **QueryHandler**: `OCPReportQueryHandler` passes context to
   `provider_map`; adds ORM filter `cost_model_context=X` when set
4. **Visibility filtering**: When `cost_model_context` is provided,
   the handler looks up the context's `data_visibility` field:
   - `cloud_and_ocp`: Current behavior — include both
     `infrastructure_raw_cost` and `cost_model_*_cost` columns
   - `ocp_only`: Substitute `cloud_infrastructure_cost` with
     `Value(0)` in the `OCPProviderMap` — cloud infrastructure
     columns are excluded from aggregation
5. **Response**: When `cost_model_context` is explicitly provided,
   include `cost_model_context` and `data_visibility` in response
   `meta`; otherwise omit both

When no context parameter is provided, the API returns all data
regardless of context — identical to today's behavior.

**Risk**: [R13](./risk-register.md#r13-was-tq-2-ocp-on-cloud-context-interaction--reopened),
[R22](./risk-register.md#r22-visibility-filtering-breaks-ocp-on-cloud-report-expectations)

---

## GA-7: Pipeline Per-Context Execution

**PRD**: Cost calculation runs per context per cluster.

**Current state**: `update_cost_model_costs` runs once per
`(schema, provider_uuid)`. `CostModelDBAccessor.cost_model` uses
`.first()`.

**Proposed implementation**:

1. **Task dispatch**: When `cost_model_context=None`,
   `update_cost_model_costs` queries `CostModelContext` for the
   tenant. If multiple contexts exist, dispatches one Celery task
   per context. If one or zero contexts, proceeds inline.

2. **Accessor**: Add optional `cost_model_context` parameter to
   `CostModelDBAccessor`. Filters `CostModelMap` by context FK.

3. **Updater chain**: Thread `cost_model_context` through
   `CostModelCostUpdater` → `OCPCostModelCostUpdater` → all
   accessor methods → SQL template parameters.

4. **SQL templates**: All 49 cost model SQL files gain
   `{{cost_model_context}}` in DELETE WHERE and INSERT columns.

5. **Cache key**: Include `cost_model_context` in the worker cache
   key to prevent dedup collisions across contexts.

**Risk**: [R2](./risk-register.md#r2-pipeline-runs-n-per-cluster),
[R5](./risk-register.md#r5-costmodeldbaccessor-single-model-assumption),
[R6](./risk-register.md#r6-sql-deleteinsert-overwrites-without-context-discriminator),
[R19](./risk-register.md#r19-celery-task-dedup-collision)

---

## GA-8: Migration — Reporting Table Context Column

**PRD**: Summary tables need a context dimension.

**Current state**: No `cost_model_context` column on any reporting table.

**Proposed implementation**:

1. **M5** (DDL): Add nullable `cost_model_context` to
   `reporting_ocpusagelineitem_daily_summary` via `AddField`
2. **M6** (DDL): Add nullable `cost_model_context` to all 13 UI
   summary tables (`reporting_ocp_*_summary_p`)
3. **M7a** (Data): RunSQL backfill on daily summary:
   `SET cost_model_context = 'default' WHERE cost_model_rate_type IS NOT NULL AND cost_model_context IS NULL`
4. **M7b** (Data): RunSQL backfill on all 13 UI summary tables
   (same WHERE clause)

**Why backfill is necessary**: The pipeline uses scoped DELETEs
(`DELETE WHERE cost_model_context = {{context}}`). Without backfill,
existing NULL rows would not be deleted, causing data duplication
on the first post-migration pipeline run.

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | Nullable + RunSQL backfill | Follows koku DDL pattern; prevents duplicates | Backfill takes time | **Proposed** |
| B | Nullable, NULL = default (no backfill) | Simpler | Scoped DELETE misses NULL rows; data duplication | Rejected |
| C | Background Celery backfill | Non-blocking | Complex; no koku precedent; hard to coordinate | Rejected |

**Risk**: [R1](./risk-register.md#r1-was-tq-3-daily-summary-migration--resolved-by-codebase-pattern),
[R11](./risk-register.md#r11-13-ui-summary-sql-files-need-context),
[R21](./risk-register.md#r21-deployment-sequencing)

---

## GA-9: Notifications — DEFERRED

**PRD (original)**: Notify when a context is missing a cost model
assignment.

**PRD (updated 2026-05-05)**: Notifications moved to **out of scope**.

**Current state**: Koku has `koku/notifications.py` with notification
helpers.

**Status**: **Deferred** per updated PRD. The implementation design
(pipeline check for missing context assignments) remains valid and
can be re-activated if notifications are brought back into scope.

---

## GA-10: Storage and Performance

**PRD**: 3 contexts × all clusters × all months = up to 3× data
volume.

**Current state**: Summary tables are already partitioned monthly.

**Proposed mitigation**: Monitor partition sizes. The context column
adds minimal per-row overhead (50 bytes). The data volume increase
is proportional to the number of contexts actually used (most tenants
will have 1-2, not 3). Retention (COST-573) already handles data
aging.

**Risk**: [R4](./risk-register.md)

---

## GA-11: Cost Visibility

**PRD (updated 2026-05-05)**: Context Assignment declares data
visibility — OpenShift-only or cloud + OpenShift per context.

**Current state**: Cloud infrastructure costs
(`infrastructure_raw_cost`, `infrastructure_markup_cost`) always
appear in OCP reports alongside cost-model-derived costs. There is
no mechanism to suppress them per context. `OCPProviderMap` already
separates these as independent ORM expressions:
- `cloud_infrastructure_cost` → `Sum(infrastructure_raw_cost)`
- `cost_model_infrastructure_cost` → sum of `cost_model_*` where
  `cost_model_rate_type = 'Infrastructure'`

**Proposed implementation**:

1. **Model**: `data_visibility` field on `CostModelContext`
   (see GA-1). Default: `cloud_and_ocp`.
2. **API filtering**: `OCPReportQueryHandler` reads the context's
   `data_visibility` when `cost_model_context` is in the request.
   For `ocp_only`: substitute `self.cloud_infrastructure_cost` with
   `Value(0, output_field=DecimalField())` in the `OCPProviderMap`
   ORM expressions. This zeroes out `infra_raw` and reduces
   `infra_total` / `cost_total` accordingly.
3. **Pipeline**: No changes. Cloud costs are written by ingestion,
   not by the cost model pipeline. Filtering is query-time only.
4. **Migration M4**: Default context gets
   `data_visibility = 'cloud_and_ocp'` (no change for existing
   users).
5. **Response meta**: Include `data_visibility` in response `meta`
   when `cost_model_context` is explicitly provided.

**Why API-layer, not pipeline-layer**:

- Cloud costs come from ingestion, not cost models — the pipeline
  cannot filter what it did not create.
- AWS `cost_type` is the direct precedent: a query parameter selects
  which columns to aggregate at query time without changing pipeline
  output.
- No data duplication — the same base data serves both visibility
  modes.

**Risk**: [R13](./risk-register.md#r13-was-tq-2-ocp-on-cloud-context-interaction--reopened),
[R22](./risk-register.md#r22-visibility-filtering-breaks-ocp-on-cloud-report-expectations)

---

## Gap Summary

| GA | Gap | Proposed Phase | Status |
|----|-----|---------------|--------|
| GA-1 | CostModelContext model | Phase 1 | Design proposed |
| GA-2 | RBAC (Koku-side v1) | Phase 4 | Design proposed |
| GA-3 | Cost model creation | — | No work needed |
| GA-4 | CostModelMap context FK | Phase 1 | Design proposed |
| GA-5 | Default metering | — | Verify with test |
| GA-6 | API query parameter | Phase 4 | Design proposed |
| GA-7 | Pipeline per-context | Phase 3 | Design proposed |
| GA-8 | Reporting table migration | Phase 2 | Design proposed |
| GA-9 | Notifications | — | **Deferred** (out of scope per updated PRD) |
| GA-10 | Storage/performance | — | Monitor |
| GA-11 | Cost visibility (`data_visibility`) | Phase 1 (model) + Phase 4 (API) | Design proposed |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-08 | Initial gap identification |
| v2.0 | 2026-04-09 | Evolved to design proposals: code sketches, migration strategy, alternatives, risk references, write-freeze rationale for GA-8 |
| v3.0 | 2026-05-05 | PRD realignment: GA-1 adds `data_visibility` field; GA-2 adds extended RBAC examples; GA-4 updates default name to "Default context" + visibility semantics; GA-6 adds visibility filtering; GA-9 deferred (notifications out of scope); GA-11 added (cost visibility) |
