# API and Frontend Changes

This document describes the cost model API modifications, the new
breakdown endpoint, and the frontend integration plan.

---

## Cost Model API Changes

### `RateSerializer` — Add `custom_name` Field

File: `cost_models/serializers.py`

`RateSerializer` currently handles `metric`, `cost_type`, `description`,
`tiered_rates`, and `tag_rates`. Add `custom_name`:

```python
class RateSerializer(serializers.Serializer):
    custom_name = serializers.CharField(max_length=50, required=True)
    metric = serializers.DictField(required=True)
    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICES, required=True)
    description = serializers.CharField(required=False, allow_blank=True)
    tiered_rates = TieredRateSerializer(many=True, required=False)
    tag_rates = TagRateSerializer(required=False)
```

**Validation rules**:

- `custom_name` is required on create
- `custom_name` must be unique within the cost model's rates (validated
  at `CostModelSerializer` level, not per-rate)
- `custom_name` max length: 50 characters

**IQ-7 PROPOSAL**: The existing `RateSerializer` does not have
`custom_name`. Proposed: add as `required=False` with auto-generation
from `description` or `metric.name` (same logic as migration M3).
This is backward compatible — existing API consumers work unchanged.
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

**Transaction safety note**: `CostModelManager.create()` already uses
`@transaction.atomic`, but `update()` does not — it only calls
`self._model.save()`. Adding `_sync_rate_table()` to `update()` means
the JSON save and the Rate table sync must be atomic. Wrap `update()`
in `@transaction.atomic` to prevent partial writes.

```python
# cost_models/cost_model_manager.py (modified)
class CostModelManager:
    def create(self, **kwargs):
        # Existing: creates CostModel with rates JSON
        cost_model = CostModel.objects.create(**cost_model_data)
        # ...existing provider mapping logic...

        # New: sync to relational tables
        self._sync_rate_table(cost_model, kwargs.get("rates", []))
        return cost_model

    @transaction.atomic   # REQUIRED: existing update() has no transaction!
    def update(self, **kwargs):
        # Existing: updates CostModel fields including rates JSON
        self.instance.rates = kwargs.get("rates", self.instance.rates)
        self.instance.save()
        # ...existing logic...

        # New: sync to relational tables
        self._sync_rate_table(self.instance, kwargs.get("rates", []))

    def _sync_rate_table(self, cost_model, rates_data):
        """Sync Rate table rows from validated rates data."""
        price_list, _ = PriceList.objects.get_or_create(
            cost_model=cost_model, defaults={"primary": True}
        )
        price_list.rates.all().delete()
        Rate.objects.bulk_create([
            Rate(
                price_list=price_list,
                custom_name=rate_data["custom_name"],
                description=rate_data.get("description", ""),
                metric=rate_data["metric"]["name"],
                metric_type=derive_metric_type(rate_data["metric"]["name"]),  # see data-model.md for mapping
                cost_type=rate_data["cost_type"],
                default_rate=extract_default_rate(rate_data),
                tag_key=rate_data.get("tag_rates", {}).get("tag_key", ""),
                tag_values=rate_data.get("tag_rates", {}).get("tag_values", {}),
            )
            for rate_data in rates_data
        ])
```

### `CostModelDBAccessor` — Read Path

File: `masu/database/cost_model_db_accessor.py`

Switch `price_list` property to read from the `Rate` table. The
dual-write approach (JSON + Rate table) ensures the JSON path can be
restored by reverting the code if needed. The output dict format must be
identical to the current JSON-based path so all downstream callers work
unchanged. See
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
        "cost_type": F("cost_type"),
    },
    "filters": ...,
    "group_by_options": ["cluster", "node", "project"],
},
```

### Response Format — Flat View (PRD Phase 1 Must-Have; Design Doc Phase 4)

**IQ-3 PROPOSAL**: The response format below shows a nested
`breakdown` array, but koku's standard query handler produces flat
annotated rows. **Proposed approach**: use the standard flat-row format
instead — each breakdown entry is a row in `data`, grouped by date.
The frontend builds the tree from `path`/`parent_path` client-side.
See [README.md § IQ-3](../cost-breakdown/README.md#iq-3-breakdown-api-response-format-phase-4).
The format below is retained for reference but will change if the
proposal is accepted.

```json
{
  "meta": {"count": 12, "currency": "USD"},
  "links": {"first": "...", "next": null, "previous": null, "last": "..."},
  "data": [
    {
      "date": "2026-02",
      "project": "my-namespace",
      "breakdown": [
        {"level": 1, "name": "Total cost", "value": 4000.00, "parent": null},
        {"level": 2, "name": "Project", "value": 2500.00, "parent": "Total cost"},
        {"level": 3, "name": "Raw cost", "value": 1000.00, "parent": "Project"},
        {"level": 4, "name": "AmazonEC2", "value": 400.00, "parent": "Raw cost"},
        {"level": 4, "name": "AmazonS3", "value": 300.00, "parent": "Raw cost"},
        {"level": 3, "name": "Usage cost", "value": 1200.00, "parent": "Project"},
        {"level": 4, "name": "OpenShift Subscriptions", "value": 500.00, "parent": "Usage cost"},
        {"level": 4, "name": "GuestOS Subscriptions", "value": 400.00, "parent": "Usage cost"},
        {"level": 4, "name": "Operation", "value": 300.00, "parent": "Usage cost"},
        {"level": 2, "name": "Overhead cost", "value": 1500.00, "parent": "Total cost"}
      ]
    }
  ]
}
```

### Response Format — Tree View (PRD Phase 2 Nice-to-Have; Design Doc Phase 4)

See PRD pages 22-25 for the nested `children` / `items` structure.
The tree view is built from the same `OCPCostUIBreakDownP` data by
grouping rows by `path` and `depth`.

### Serializer

New serializer in `api/report/ocp/serializers.py` (or a new file):

```python
class CostBreakdownItemSerializer(serializers.Serializer):
    level = serializers.IntegerField(source="depth")
    name = serializers.CharField(source="custom_name")
    value = serializers.DecimalField(source="cost_value", max_digits=33, decimal_places=15)
    parent = serializers.CharField(source="parent_path")

class CostBreakdownSerializer(serializers.Serializer):
    date = serializers.CharField()
    project = serializers.CharField(required=False)
    cluster = serializers.CharField(required=False)
    breakdown = CostBreakdownItemSerializer(many=True)
```

### Pagination

Database-level pagination per PRD:

- `LIMIT/OFFSET` at SQL level via Django's `Paginator`
- Separate `COUNT(*)` for `meta.count`
- Consistent `ORDER BY path, depth` before pagination
- All filter/order columns are indexed

### No Feature Flags

No feature flags are used for any part of this feature. The breakdown
endpoint returns empty results if `OCPCostUIBreakDownP` is not populated
(Phases 1-3). Phase 4 populates the table and the endpoint starts
returning data. The dual-write approach (JSON + Rate table) is the
rollback mechanism for the backend schema changes — reverting code
restores the JSON read path.

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
