# API and Frontend Changes

This document describes the cost model API modifications, the new
breakdown endpoint, and the frontend integration plan.

---

## Cost Model API Changes

### `RateSerializer` — Add `custom_name` and `rate_id` Fields

File: `cost_models/serializers.py`

`RateSerializer` currently handles `metric`, `cost_type`, `description`,
`tiered_rates`, and `tag_rates`. Add `custom_name` and `rate_id`:

```python
class RateSerializer(serializers.Serializer):
    rate_id = serializers.UUIDField(required=False, allow_null=True)
    custom_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
    metric = serializers.DictField(required=True)
    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICES, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    tiered_rates = TieredRateSerializer(many=True, required=False)
    tag_rates = TagRateSerializer(required=False)

    def to_representation(self, rate_obj):
        out = super().to_representation(rate_obj)
        # rate_obj is a dict from the JSON blob — rate_id is injected
        # during dual-write (see _sync_rate_table). The existing
        # to_representation builds a fixed output dict; rate_id must be
        # added explicitly since the base method only emits declared
        # fields that are present in rate_obj.
        if "rate_id" in rate_obj:
            out["rate_id"] = rate_obj["rate_id"]
        return out
```

**`rate_id` field notes**:

- `rate_id` is the `Rate.uuid` (primary key). It is read-write:
  GET responses include it; PUT requests may include it.
- `rate_id` must be declared as an explicit field (not rely on the
  custom `to_internal_value()` passthrough, which is fragile).
- `to_representation()` must explicitly include `rate_id` because the
  existing implementation builds a fixed output dict from the JSON blob
  and does not pass through arbitrary extra keys.
- `rate_id` is injected into the JSON blob during dual-write (see
  `_sync_rate_table` below), so it is available in `rate_obj` for
  GET serialization.

**`custom_name` validation rules**:

- `custom_name` is optional — if not provided, auto-generated from
  `description` or `metric.name` (same logic as migration M2)
- `custom_name` must be unique within the cost model's rates (validated
  at `CostModelSerializer` level, not per-rate)
- `custom_name` max length: 50 characters

**IQ-7 RESOLVED**: Tech lead confirmed. `custom_name` is added as
`required=False` with auto-generation from `description` or
`metric.name` (same logic as migration M2). This is backward
compatible — existing API consumers work unchanged.
See [README.md § IQ-7](../cost-breakdown/README.md#iq-7-backward-compatibility-for-custom_name-phase-1).

### `CostModelSerializer` — Dual-Write

File: `cost_models/serializers.py`

On `create()` and `update()`, the serializer delegates to
`CostModelManager` (not direct ORM). During the dual-write period
(Phases 1-4), the manager writes to both JSON and relational tables.

**Important**: `CostModelSerializer.create()` calls
`CostModelManager().create()`, and `update()` calls
`CostModelManager.update()`. The dual-write logic belongs in
`CostModelManager`, not in the serializer.

**Transaction safety note**: `CostModelManager.update()` already has
`@transaction.atomic` (added by COST-575 PR #5963). Adding
`_sync_rate_table()` to `update()` means the JSON save, PriceList.rates
sync, and Rate table sync are all atomic — no additional wrapping needed.

```python
# cost_models/cost_model_manager.py (modified — extends COST-575 dual-write)
class CostModelManager:
    @transaction.atomic  # already present from COST-575
    def create(self, **kwargs):
        # Existing: creates CostModel with rates JSON
        cost_model = CostModel.objects.create(**cost_model_data)
        # ...existing provider mapping logic...

        # COST-575: _get_or_create_price_list() already creates PriceList + mapping
        # New: sync to Rate table
        if self._model.rates:
            pl = self._get_or_create_price_list()  # existing COST-575 method
            self._sync_rate_table(pl, kwargs.get("rates", []))
        return cost_model

    @transaction.atomic   # already present from COST-575
    def update(self, **kwargs):
        # Existing: updates CostModel fields including rates JSON
        self._model.rates = kwargs.get("rates", self._model.rates)
        self._model.save()

        # COST-575: syncs PriceList.rates JSON
        if "rates" in kwargs:
            pl = self._get_or_create_price_list()
            if pl:
                pl.rates = self._model.rates
                pl.save(update_fields=["rates", "updated_timestamp"])
                # New: sync to Rate table
                self._sync_rate_table(pl, kwargs.get("rates", []))

    def _sync_rate_table(self, price_list, rates_data):
        """Diff-based sync of Rate table rows.

        Matches incoming rates to existing Rate rows by rate_id (if
        present) or custom_name (backward-compat fallback). Operations
        are ordered delete → update → create to avoid transient
        UniqueConstraint violations on (price_list, custom_name).

        After sync, injects rate_id (Rate.uuid) back into the JSON
        blob so GET responses include it.
        """
        existing = {r.uuid: r for r in price_list.rate_rows.all()}
        existing_by_name = {r.custom_name: r for r in existing.values()}
        incoming_ids = set()
        to_update = []
        to_create = []

        for rate_data in rates_data:
            rate_id = rate_data.get("rate_id")
            if rate_id:
                if rate_id not in existing:
                    raise CostModelException(f"Invalid rate_id: {rate_id}")
                # Validate ownership: rate_id must belong to this price_list
                rate_obj = existing[rate_id]
                incoming_ids.add(rate_id)
                to_update.append((rate_obj, rate_data))
            else:
                # Backward-compat: match by custom_name if no rate_id
                name = rate_data.get("custom_name") or generate_custom_name(rate_data)
                if name in existing_by_name:
                    rate_obj = existing_by_name[name]
                    incoming_ids.add(rate_obj.uuid)
                    to_update.append((rate_obj, rate_data))
                else:
                    to_create.append(rate_data)

        # Phase 1: delete → update → create (ordering avoids unique constraint violations)
        to_delete = [r for uid, r in existing.items() if uid not in incoming_ids]
        for rate_obj in to_delete:
            rate_obj.delete()

        for rate_obj, rate_data in to_update:
            changed = self._apply_rate_fields(rate_obj, rate_data)
            if changed:
                rate_obj.save()
            rate_data["rate_id"] = str(rate_obj.uuid)

        for rate_data in to_create:
            rate_obj = Rate.objects.create(
                price_list=price_list,
                **self._rate_fields_from_data(rate_data),
            )
            rate_data["rate_id"] = str(rate_obj.uuid)

        # Inject rate_id back into JSON blobs for GET serialization
        self._model.rates = rates_data
        self._model.save(update_fields=["rates"])
        price_list.rates = rates_data
        price_list.save(update_fields=["rates", "updated_timestamp"])

    COST_AFFECTING_FIELDS = {"default_rate", "tag_values", "metric", "cost_type"}

    def _apply_rate_fields(self, rate_obj, rate_data):
        """Update rate_obj fields from rate_data. Returns True if any
        cost-affecting field changed (requires recalculation)."""
        fields = self._rate_fields_from_data(rate_data)
        changed = False
        for attr, value in fields.items():
            if getattr(rate_obj, attr) != value:
                setattr(rate_obj, attr, value)
                if attr in self.COST_AFFECTING_FIELDS:
                    changed = True
        return changed

    @staticmethod
    def _rate_fields_from_data(rate_data):
        """Extract Rate model fields from a rate data dict."""
        tag_rates = rate_data.get("tag_rates", {})
        return {
            "custom_name": rate_data.get("custom_name") or generate_custom_name(rate_data),
            "description": rate_data.get("description", ""),
            "metric": rate_data["metric"]["name"],
            "metric_type": derive_metric_type(rate_data["metric"]["name"]),
            "cost_type": rate_data["cost_type"],
            "default_rate": extract_default_rate(rate_data),
            "tag_key": tag_rates.get("tag_key", ""),
            "tag_values": tag_rates.get("tag_values", []),
        }
```

**Diff-based sync design decisions**:

- **Backward compatibility**: When `rate_id` is absent from the payload,
  the backend matches by `custom_name` (using the existing
  `unique_together` constraint). This preserves `Rate.uuid` for
  unchanged rates even before the frontend ships `rate_id` support.
  Renaming a rate without `rate_id` behaves as delete + create (the
  old name is unmatched, the new name is created).
- **Validation**: `rate_id` is validated for both existence AND
  ownership — it must belong to the correct price_list. This prevents
  a user from referencing a `rate_id` from a different cost model
  within the same schema.
- **Operation ordering**: Deletes run first, then updates, then creates.
  This avoids transient `UniqueConstraint` violations on
  `(price_list, custom_name)` when a rate is renamed and a new rate
  takes its old name in the same request.
- **Change detection**: `COST_AFFECTING_FIELDS` defines which fields
  trigger recalculation. Metadata-only changes (`description`,
  `custom_name`) update the Rate row but do not trigger the Celery
  recalculation task. Phase 1 uses a conservative approach — any
  cost-affecting field change triggers full-window recalculation
  (current month). Scoped per-rate recalculation is a future
  optimization (see below).
- **`rate_id` injection**: After sync, `rate_id` (as string UUID) is
  injected back into `rates_data` and saved to both `CostModel.rates`
  and `PriceList.rates` JSON blobs. This ensures GET responses include
  `rate_id` without changing the read path.

**Scoped recalculation — deferred optimization**:

Phase 1 triggers full-window recalculation (current month) on any
cost-affecting change, regardless of how many rates changed. This is
the existing behavior and is correct.

Scoped recalculation (passing `affected_rate_ids` to the Celery task
so only changed rates are reprocessed) requires non-trivial changes to
the `update_cost_model_costs` task signature, worker cache dedup key,
and the monolithic `update_summary_cost_model_costs()` pipeline in
`ocp_cost_model_cost_updater.py`. The aggregation step must still
process all rates (it's a SUM over all `RatesToUsage` rows), so savings
are limited to the INSERT step. This optimization is deferred to a
future phase.

### `CostModelDBAccessor` — Read Path

File: `masu/database/cost_model_db_accessor.py`

Switch `price_list` property to read from the `Rate` table. The query
path is: `CostModel → PriceListCostModelMap → PriceList → Rate`. The
dual-write approach (JSON + PriceList.rates + Rate table) ensures the
JSON path can be restored by reverting the code if needed. The output
dict format must be identical to the current JSON-based path so all
downstream callers work unchanged. See
[sql-pipeline.md § CostModelDBAccessor Changes](./sql-pipeline.md#costmodeldbcaccessor-changes).

---

## New Breakdown Endpoint

### URL

```
GET /api/cost-management/v1/breakdown/openshift/cost/
```

Registered in `api/urls.py` alongside existing report URLs:

```python
# api/urls.py
urlpatterns = [
    ...
    path("breakdown/openshift/cost/", OCPCostBreakdownView.as_view(), name="ocp-cost-breakdown"),
]
```

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filter[time_scope_units]` | string | No | `month` or `day` |
| `filter[time_scope_value]` | integer | No | `-1` (current), `-2` (previous) |
| `filter[resolution]` | string | No | `daily`, `monthly` |
| `filter[path]` | string | No | Filter to subtree, e.g. `project.usage_cost` |
| `group_by[project]` | string | No | Namespace filter |
| `group_by[cluster]` | string | No | Cluster filter |
| `group_by[node]` | string | No | Node filter |
| `view` | string | No | `flat` (default) or `tree` |

### View Class

File: `api/report/ocp/view.py` (new class)

```python
class OCPCostBreakdownView(OCPView):
    """View for cost breakdown by rate."""
    report = "cost_breakdown"
```

Uses the existing `OCPView` base class (which inherits from `ReportView`)
to ensure RBAC permissions are consistent. The `report` attribute maps
to the provider map entry.

### Provider Map Entry

File: `api/report/ocp/provider_map.py`

Add `cost_breakdown` to `OCPProviderMap`:

```python
"cost_breakdown": {
    "tables": {
        "query": OCPCostUIBreakDownP,
    },
    "aggregates": {
        "cost_value": Sum("cost_value"),
        "distributed_cost": Sum("distributed_cost"),
    },
    "annotations": {
        "custom_name": F("custom_name"),
        "path": F("path"),
        "depth": F("depth"),
        "parent_path": F("parent_path"),
        "top_category": F("top_category"),
        "breakdown_category": F("breakdown_category"),
        "metric_type": F("metric_type"),
    },
    "filters": ...,
    "group_by_options": ["cluster", "node", "project"],
},
```

### Response Format — Flat View (IQ-3 RESOLVED; Design Doc Phase 4)

**IQ-3 resolved**: The database stores flat rows. The API serves
**both** flat and nested response formats (controlled by `?view=flat`
or `?view=tree`). The flat view is the default and follows koku's
standard `OCPReportQueryHandler` output convention — flat annotated
rows grouped by date and `group_by` parameters.

```json
{
  "meta": {"count": 12, "currency": "USD"},
  "links": {"first": "...", "next": null, "previous": null, "last": "..."},
  "data": [
    {
      "date": "2026-02",
      "project": "my-namespace",
      "values": [
        {"depth": 1, "custom_name": "total_cost", "path": "total_cost", "parent_path": "", "cost_value": 4000.00, "distributed_cost": null, "metric_type": "total"},
        {"depth": 2, "custom_name": "project", "path": "project", "parent_path": "total_cost", "cost_value": 2500.00, "distributed_cost": null, "metric_type": "total"},
        {"depth": 3, "custom_name": "usage_cost", "path": "project.usage_cost", "parent_path": "project", "cost_value": 1200.00, "distributed_cost": null, "metric_type": "total"},
        {"depth": 4, "custom_name": "OpenShift Subscriptions", "path": "project.usage_cost.OpenShift_Subscriptions", "parent_path": "project.usage_cost", "cost_value": 500.00, "distributed_cost": null, "metric_type": "cpu"}
      ]
    }
  ]
}
```

### Response Format — Tree View (IQ-3 RESOLVED; Design Doc Phase 4)

The tree view is built from the same `OCPCostUIBreakDownP` flat rows.
When `?view=tree` is requested, the API reconstructs the hierarchy
from `path`/`parent_path` and returns a nested `children` structure.
See PRD pages 22-25 for the nested `children` / `items` structure.

```json
{
  "meta": {"count": 1, "currency": "USD"},
  "data": [
    {
      "date": "2026-02",
      "project": "my-namespace",
      "tree": {
        "custom_name": "total_cost",
        "cost_value": 4000.00,
        "children": [
          {
            "custom_name": "project",
            "cost_value": 2500.00,
            "children": [
              {"custom_name": "usage_cost", "cost_value": 1200.00, "children": []}
            ]
          }
        ]
      }
    }
  ]
}
```

### Serializers

New serializers in `api/report/ocp/serializers.py` (or a new file):

```python
class CostBreakdownFlatItemSerializer(serializers.Serializer):
    depth = serializers.IntegerField()
    custom_name = serializers.CharField()
    path = serializers.CharField()
    parent_path = serializers.CharField()
    cost_value = serializers.DecimalField(max_digits=33, decimal_places=15)
    distributed_cost = serializers.DecimalField(max_digits=33, decimal_places=15, allow_null=True)
    metric_type = serializers.CharField()

class CostBreakdownTreeNodeSerializer(serializers.Serializer):
    custom_name = serializers.CharField()
    cost_value = serializers.DecimalField(max_digits=33, decimal_places=15)
    distributed_cost = serializers.DecimalField(max_digits=33, decimal_places=15, allow_null=True)
    metric_type = serializers.CharField()
    children = serializers.ListField(child=serializers.DictField(), required=False)
```

The view class determines which serializer to use based on the `view`
query parameter (defaults to flat).

### Pagination

Database-level pagination per PRD:

- `LIMIT/OFFSET` at SQL level via Django's `Paginator`
- Separate `COUNT(*)` for `meta.count`
- Consistent `ORDER BY path, depth` before pagination
- All filter/order columns are indexed

### Migration Write-Freeze Flag (Unleash)

An Unleash feature flag gates cost model API writes during critical
migration windows to prevent data corruption from concurrent writes.

**Flag name**: `cost-management.backend.disable-cost-model-writes`

**Convention**: Follows the existing "enable flag to disable writes"
pattern used by `is_cloud_source_processing_disabled` and
`is_summary_processing_disabled` in `masu/processor/__init__.py`.

**Helper function** (new, in `masu/processor/__init__.py`):

```python
COST_MODEL_WRITE_FREEZE_FLAG = "cost-management.backend.disable-cost-model-writes"

def is_cost_model_writes_disabled(schema):  # pragma: no cover
    """Disable cost model writes during migration windows."""
    context = {"schema": schema}
    res = UNLEASH_CLIENT.is_enabled(COST_MODEL_WRITE_FREEZE_FLAG, context)
    if res:
        LOG.info(log_json(msg="cost model writes disabled for migration", context=context))
    return res
```

**Gating in `CostModelSerializer`** (in `cost_models/serializers.py`):

The check belongs in the serializer — not `CostModelManager` — because
`validated_data` does not carry a `schema` key, while the serializer
already accesses `self.customer.schema_name` for provider validation.

```python
from masu.processor import is_cost_model_writes_disabled

class CostModelSerializer(BaseSerializer):
    # ... existing fields ...

    def create(self, validated_data):
        schema = self.customer.schema_name if self.customer else None
        if schema and is_cost_model_writes_disabled(schema):
            raise serializers.ValidationError(
                error_obj("cost-models", "Cost model writes are temporarily disabled during migration.")
            )
        source_uuids = validated_data.pop("source_uuids", [])
        validated_data.update({"provider_uuids": source_uuids})
        try:
            return CostModelManager().create(**validated_data)
        except CostModelException as error:
            raise serializers.ValidationError(error_obj("cost-models", str(error)))

    def update(self, instance, validated_data, *args, **kwargs):
        schema = self.customer.schema_name if self.customer else None
        if schema and is_cost_model_writes_disabled(schema):
            raise serializers.ValidationError(
                error_obj("cost-models", "Cost model writes are temporarily disabled during migration.")
            )
        # ... existing update logic (CostModelManager().update) ...
```

**API response**: `serializers.ValidationError` with a write-freeze
message is returned by the serializer. The view should catch this
specific case and return `HTTP 503 Service Unavailable` with a
`Retry-After` header. This follows the HTTP semantics for temporary
unavailability and matches the existing `CostModelException` handling
pattern.

**When to enable / disable**:

| Window | Enable before | Disable after |
|--------|--------------|---------------|
| M2 data migration (Phase 1) | `django-admin migrate` for M2 | M2 completes + validation passes |
| M5 column drop (Phase 5) | `django-admin migrate` for M5 | M5 completes + regression passes |

**On-prem behavior**: `MockUnleashClient` returns `False` by default,
so the write-freeze flag is never active on-prem. On-prem deployments
manage migration windows through operator coordination (maintenance
window in `koku-metrics-operator`).

**No other feature flags** are used for this feature. The breakdown
endpoint returns empty results if `OCPCostUIBreakDownP` is not populated
(Phases 1-3). Phase 4 populates the table and the endpoint starts
returning data. The dual-write approach (JSON + Rate table) remains the
rollback mechanism for schema changes — reverting code restores the JSON
read path.

---

## Frontend Changes

All frontend changes target the `koku-ui` repository
(`project-koku/koku-ui`, forked to `jordigilh/koku-ui`).

### New Report Type

File: `apps/koku-ui-hccm/src/api/reports/report.ts`

```typescript
export const enum ReportType {
  cost = 'cost',
  costBreakdown = 'costBreakdown',  // NEW
  cpu = 'cpu',
  // ...
}
```

File: `apps/koku-ui-hccm/src/api/reports/ocpReports.ts`

```typescript
export const ReportTypePaths: Partial<Record<ReportType, string>> = {
  [ReportType.cost]: 'reports/openshift/costs/',
  [ReportType.costBreakdown]: 'breakdown/openshift/cost/',  // NEW
  // ...
};
```

### New Flat List Component

Location: `apps/koku-ui-hccm/src/routes/details/components/costOverview/`

New component: `CostBreakdownTable` — renders the flat list view from
the breakdown API response.

- Uses PatternFly `Table` (existing `DataTable` wrapper)
- Columns: Level, Name, Value, Parent
- Indentation based on `level` for visual hierarchy
- Sortable by value

### Tree View Component (Phase 2)

Location: same directory

New component: `CostBreakdownTree` — renders the tree view using
PatternFly `TreeView` component.

- **New dependency**: `TreeView` is not currently used in koku-ui.
  It is available in `@patternfly/react-core` (already installed)
  but has not been imported anywhere in the project.
- Transforms flat breakdown data into tree structure client-side
  (group by `parent` field)

### Tab Restructuring

File: `apps/koku-ui-hccm/src/routes/details/components/breakdown/breakdownBase.tsx`

Current tabs: Cost Overview | Historical Data | Instances | Optimizations | Virtualization

New tabs: **Cost Overview** | **Usage Overview** (new) | Historical Data | Instances | Optimizations | Virtualization

- **Cost Overview** keeps: Sankey chart + new breakdown table (flat/tree)
- **Usage Overview** (new tab) gets: CPU, Memory, Storage, GPU usage cards
  (moved from Cost Overview)

### Cost Overview Widget

File: `apps/koku-ui-hccm/src/store/breakdown/costOverview/common/costOverviewCommon.ts`

Add new widget type:

```typescript
export const enum CostOverviewWidgetType {
  costBreakdown = 'costBreakdown',       // existing Sankey
  costBreakdownTable = 'costBreakdownTable', // NEW flat/tree table
  // ...
}
```

### Export Integration

File: `apps/koku-ui-hccm/src/api/export/ocpExport.ts`

The existing `runExport` function already uses `ReportTypePaths` for all
report types, including export (sends `Accept: text/csv`). Since the
breakdown path is registered in `ReportTypePaths`, export works
automatically — no separate export function is needed:

```typescript
// ocpExport.ts (unchanged — works for all report types including costBreakdown)
export function runExport(reportType: ReportType, query: string) {
  const path = ReportTypePaths[reportType];
  return axiosInstance.get<string>(`${path}?${query}`, {
    headers: { Accept: 'text/csv' },
  });
}
```

This follows the same convention used by virtualization
(`reports/openshift/resources/virtual-machines/`) and all other OCP
report types.

CSV columns per PRD: `Project, Level 1 (Category), Level 2 (Sub-Category), Metric, Name, Cost`

### Existing Components — No Changes

| Component | File | Why Unchanged |
|-----------|------|---------------|
| `CostBreakdownChart` (Sankey) | `costBreakdownChart.tsx` | Reads from existing `/reports/openshift/costs/` via `report.meta.total.cost` |
| `ExportModal` | `exportModal.tsx` | Extended (not replaced) with breakdown export option |
| `OcpDetails` | `ocpDetails.tsx` | Main details table unchanged |
| Report API calls | `ocpReports.ts` | Existing endpoints unchanged |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-17 | Initial: OCPReportQueryHandler extension, CostBreakdownView, serializers, response format, frontend integration plan (PatternFly TreeTable, CSV export), existing component audit. |
| v2.0 | 2026-03-17 | Fix _sync_rate_table to use bulk_create instead of loop. Update IQ-7 from PROPOSAL to RESOLVED (auto-generated custom_name confirmed). |
| v2.2 | 2026-03-17 | IQ-3 resolved: split single serializer into CostBreakdownFlatItemSerializer + CostBreakdownTreeNodeSerializer. Add ?view=tree query param. Update flat and tree JSON response examples. |
| v2.3 | 2026-03-17 | Blast-radius triage: fix RateSerializer `custom_name` from `required=True` to `required=False` (align with IQ-7 resolution). Update validation rules. |
| v3.0 | 2026-03-19 | **IQ-8 RESOLVED.** Drop `cost_type` from provider map, serializers, and JSON examples (PM + tech lead confirmed not needed). |
| v4.0 | 2026-04-02 | **Align with COST-575.** Update `_sync_rate_table` to use existing `PriceList` via `_get_or_create_price_list()` (COST-575 method). `related_name` is `rate_rows`. `@transaction.atomic` already present from COST-575. Update read path to query through `PriceListCostModelMap`. |
| v4.1 | 2026-04-02 | **Migration write-freeze flag (R20).** Replace "No Feature Flags" section with Unleash write-freeze flag (`cost-management.backend.disable-cost-model-writes`). Add helper function, `CostModelManager` gating, HTTP 503 behavior, enable/disable windows, on-prem behavior. |
| v4.2 | 2026-04-02 | **Critical review.** Move write-freeze gating from `CostModelManager` to `CostModelSerializer` — `validated_data` lacks schema context; serializer has `self.customer.schema_name`. Add `@transaction.atomic` to `create()` pseudocode. |
