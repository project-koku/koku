# Efficiency scores — formulas and API data contract

Companion to [README.md](./README.md). Describes the **implemented** backend behavior for CPU and memory **usage efficiency** and **wasted cost** on OpenShift compute/memory reports.

---

## Canonical data fields (CPU / memory)

Aggregates are defined on **`OCPUsageLineItemDailySummary`** (LIDS) in [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py) for `report_type` **`cpu`** and **`memory`**.

| Metric | LIDS column (hours) | Used by |
|--------|---------------------|---------|
| CPU usage | `pod_usage_cpu_core_hours` | `usage_efficiency_percent` |
| CPU request | `pod_request_cpu_core_hours` | `usage_efficiency_percent` |
| CPU effective | `pod_effective_usage_cpu_core_hours` | `wasted_cpu_cost` (pipeline) |
| Memory usage | `pod_usage_memory_gigabyte_hours` | `usage_efficiency_percent` |
| Memory request | `pod_request_memory_gigabyte_hours` | `usage_efficiency_percent` |
| Memory effective | `pod_effective_usage_memory_gigabyte_hours` | `wasted_memory_cost` (pipeline) |

`pod_effective_usage_*` is the daily sum of `MAX(usage, request)` per pod-hour from the operator — always `>= usage` and `>= request`.

Sums use `Coalesce(..., 0)` via helpers such as [`_cpu_usage_sum`](../../../koku/api/report/ocp/provider_map.py) / [`_memory_request_sum`](../../../koku/api/report/ocp/provider_map.py).

---

## Usage efficiency (`usage_efficiency_percent`)

### Definition (implemented)

Computed **at API query time** by the ORM. Let **`usage_sum`** and **`request_sum`** be the **Sum** expressions for the appropriate resource for the current aggregate (total or group).

| Expression | Meaning |
|------------|---------|
| Ratio | `usage_sum / NULLIF(request_sum, 0)` — avoids division by zero. |
| **Percent** | `Round(ratio * 100)` as **integer** (Django `Round` + `IntegerField` in [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py)). |
| **Null / zero request** | `Coalesce(..., 0)` → API exposes **`0`** when the ratio is null (including **`request_sum == 0`**). |

So **`usage_efficiency_percent` can exceed 100** when usage exceeds request over the aggregated rows (not clamped).

ORM annotation in [`provider_map.py`](../../../koku/api/report/ocp/provider_map.py) (cpu ~lines 404–419):

```python
"usage_efficiency": Coalesce(
    Round(
        Sum(pod_usage_cpu_core_hours)
        / NullIf(Sum(pod_request_cpu_core_hours), 0)
        * 100
    ),
    Value(0),
)
```

### API field name

Response shaping is done in [`OCPReportQueryHandler._pack_score`](../../../koku/api/report/ocp/query_handler.py): the internal annotation `usage_efficiency` is exposed as **`usage_efficiency_percent`**.

---

## Wasted cost (`wasted_cost`)

### Where it is computed

`wasted_cost` is **not** computed at API query time. It is **pre-computed during the cost model pipeline** in [`aggregate_rates_to_daily_summary.sql`](../../../koku/masu/database/sql/openshift/cost_model/usage_rates/aggregate_rates_to_daily_summary.sql) and stored as physical columns `wasted_cpu_cost` / `wasted_memory_cost` on LIDS cost model rows and on the three pod summary tables. The API ORM annotation simply sums the pre-computed values.

### Pipeline context

The pipeline runs in two phases before the UI summary SQL fires:

**Phase 1 — [`insert_usage_rates_to_usage.sql`](../../../koku/masu/database/sql/openshift/cost_model/usage_rates/insert_usage_rates_to_usage.sql)**

Reads LIDS base rows and writes one row per metric per base row into the `rates_to_usage` staging table:

| Metric | `calculated_cost` |
|--------|-------------------|
| `cpu_core_usage_per_hour` | `cpu_usage_hours * rate` |
| `cpu_core_request_per_hour` | `cpu_request_hours * rate` |
| `cpu_core_effective_usage_per_hour` | `cpu_effective_hours * rate` |
| `memory_gb_usage_per_hour` | `mem_usage_hours * rate` |
| `memory_gb_request_per_hour` | `mem_request_hours * rate` |
| `memory_gb_effective_usage_per_hour` | `mem_effective_hours * rate` |
| *(plus storage, node hourly, cluster hourly)* | … |

**Phase 2 — [`aggregate_rates_to_daily_summary.sql`](../../../koku/masu/database/sql/openshift/cost_model/usage_rates/aggregate_rates_to_daily_summary.sql)**

Deletes and re-inserts LIDS cost model rows (grouped by label-set / node / namespace / day). Writes `cost_model_cpu_cost`, `cost_model_memory_cost`, `cost_model_volume_cost`, **`wasted_cpu_cost`**, and **`wasted_memory_cost`**.

### Pipeline formula (implemented)

Applied **per LIDS cost-model row** (label-set / node / namespace / day grain):

```sql
GREATEST(0,
    SUM(CASE WHEN rtu.metric_type = 'cpu' THEN rtu.calculated_cost ELSE 0 END)
    * (1 - MAX(base.cpu_usage_hours) / NULLIF(MAX(base.cpu_effective_hours), 0))
)
```

Where:
- `SUM(...calculated_cost)` — total CPU cost across all CPU rate metrics for this LIDS row.
- `cpu_usage_hours` — `pod_usage_cpu_core_hours` from the base LIDS row (actual consumption).
- `cpu_effective_hours` — `pod_effective_usage_cpu_core_hours` from the base LIDS row (`MAX(usage, request)` per pod-hour, daily sum).

The same formula applies for memory (`wasted_memory_cost`), substituting memory columns.

**Key property:** dividing by `effective_hours` (not `request_hours`) means waste is the cost of the gap between actual usage and the effective ceiling — the amount that could have been reclaimed while still satisfying all requests.

When `cpu_effective_hours` is zero, `NULLIF` makes the ratio `NULL`; both columns default to `0` via `COALESCE` in the UI summary SQL.

### Cost basis

`wasted_cpu_cost` covers **only `cost_model_cpu_cost`** — the cost accrued from CPU usage/request/effective-usage rates configured in the cost model. It does **not** include `cloud_infrastructure_cost`, `markup_cost`, or distribution costs.

### Storage in summary tables

After Phase 2 writes `wasted_cpu_cost` / `wasted_memory_cost` to LIDS, the UI summary SQL rolls them up with a straightforward aggregate (no formula re-derivation):

```sql
SUM(COALESCE(wasted_cpu_cost, 0))    AS wasted_cpu_cost,
SUM(COALESCE(wasted_memory_cost, 0)) AS wasted_memory_cost
```

This runs in:
- [`reporting_ocp_pod_summary_p.sql`](../../../koku/masu/database/sql/openshift/ui_summary/reporting_ocp_pod_summary_p.sql) — cluster grain
- [`reporting_ocp_pod_summary_by_project_p.sql`](../../../koku/masu/database/sql/openshift/ui_summary/reporting_ocp_pod_summary_by_project_p.sql) — namespace grain
- [`reporting_ocp_pod_summary_by_node_p.sql`](../../../koku/masu/database/sql/openshift/ui_summary/reporting_ocp_pod_summary_by_node_p.sql) — node grain

Migration [`0351`](../../../koku/reporting/migrations/0351_pod_summary_wasted_cost.py) added `wasted_cpu_cost` / `wasted_memory_cost` to LIDS and all three summary tables.

### API query table selection

The API selects a backing table via the `query_table` property in [`queries.py`](../../../koku/api/report/queries.py). It builds a key tuple from the union of all `group_by`, `filter`, `access`, and `exclude` keys, then looks up the matching table in the `views` dict in [`provider_map.py`](../../../koku/api/report/ocp/provider_map.py):

| Key tuple | Table |
|-----------|-------|
| `"default"` | `OCPPodSummaryP` |
| `("cluster",)` | `OCPPodSummaryP` |
| `("node",)` | `OCPPodSummaryByNodeP` |
| `("project",)` | `OCPPodSummaryByProjectP` |
| `("cluster", "project")` | `OCPPodSummaryByProjectP` |
| `("cluster", "node")` | `OCPPodSummaryByNodeP` |
| *any other combination* | **`OCPUsageLineItemDailySummary` (LIDS fallback)** |

The LIDS fallback matters: cross-dimensional combinations like `group_by[node]` + `filter[project]` produce a key tuple with no entry in the dict and fall through to LIDS. Because `wasted_cpu_cost` is now written directly onto LIDS cost model rows by Phase 2, the LIDS fallback path returns real waste values (previously it always returned 0 — see Changelog).

### API ORM annotation

The provider map does **not** re-derive waste at query time. The annotation is a currency-adjusted sum of the pre-computed column (see [`provider_map.py`](../../../koku/api/report/ocp/provider_map.py), cpu ~lines 420–433, memory ~lines 635–648):

```python
"wasted_cost": Coalesce(
    Sum(
        Coalesce(F("wasted_cpu_cost"), Value(0, ...))
        * Coalesce(F("exchange_rate"), Value(1, ...))
    ),
    Value(0, ...),
)
```

### API shape

```json
"wasted_cost": {
  "value": "<Decimal>",
  "units": "<user currency from report context>"
}
```

`units` comes from the handler's currency (`self.currency` in [`_pack_score`](../../../koku/api/report/ocp/query_handler.py)).

### Accuracy limitation

The formula is applied at the LIDS-row grain (label-set / node / namespace / day). Pods that share the same label hash are aggregated before the formula runs, which introduces a small approximation for usage-based metrics (`cpu_core_usage_per_hour`, `cpu_core_request_per_hour`). The formula is **exact** for `cpu_core_effective_usage_per_hour` because cost decomposes additively when using effective hours.

**Worked example — two pods, same namespace, one day:**

- Pod A: 2 CPU-hours used, 4 effective CPU-hours. Cost = `2 * $1 = $2`.
- Pod B: 1 CPU-hour used, 4 effective CPU-hours. Cost = `1 * $1 = $1`.

Exact wasted cost per pod:
- Pod A: `$2 * (1 - 2/4) = $1.00`
- Pod B: `$1 * (1 - 1/4) = $0.75`
- **Exact total: $1.75**

If the pods have **different label hashes** (different LIDS rows), Phase 2 computes each row independently → **$1.75 ✓ exact**.

If the pods share the **same label hash** (same LIDS row):
- Row AB: `cost = $3`, `usage = 3`, `effective = 8` → `$3 * (1 - 3/8) = $1.875`
- **Total: $1.875** (approximation — same as the previous namespace-grain formula)

The residual error occurs only when pods with meaningfully different `usage/request` ratios share a label group. In practice this is rare; pods with different resource profiles typically carry different labels (`app`, `workload`, `tier`). The LIDS-grain formula is significantly more accurate than the previous namespace-grain approach.

The remaining error for usage-based metrics is inherent to daily-grain data — computing $1.75 exactly when both pods share a label would require sub-daily per-pod data that is not stored.

---

## Fleet vs grouped rows

- **Total row:** `query.aggregate(**aggregates)` sums `wasted_cpu_cost * exchange_rate` and computes the `usage_efficiency` ratio over the **entire filtered queryset** — one combined value for the fleet.
- **Grouped rows:** Each group gets its own slice of the same `SUM` expressions from `values(...).annotate(...)`.

---

## When scores are absent or empty

The guard in [`query_handler.py`](../../../koku/api/report/ocp/query_handler.py):

```python
has_tag_interaction = self._tag_group_by or self.get_tag_filter_keys()
should_compute = not has_tag_interaction and len(group_by_value) <= 1
```

When `should_compute` is `False`, both `wasted_cost` and `usage_efficiency` are popped from the response entirely.

| Situation | `total.total_score` | Row `score` |
|-----------|---------------------|-------------|
| `report_type` not `cpu` / `memory` | Key **omitted** | N/A |
| `cpu` / `memory`, multiple `group_by` keys | `{}` | `{}` |
| `cpu` / `memory`, tag `group_by` or tag keys under **`filter`** | `{}` | `{}` |
| `cpu` / `memory`, tag keys under **`exclude` only** (no tag `group_by`, no tag `filter`) | Populated | Populated |
| Otherwise | Populated | Populated |

Source: [`OCPReportQueryHandler.execute_query`](../../../koku/api/report/ocp/query_handler.py) (`should_compute`).

---

## Ordering

`order_by[usage_efficiency]` and `order_by[wasted_cost]` are valid on inventory serializers ([`InventoryOrderBySerializer`](../../../koku/api/report/ocp/serializers.py)). Sorting uses the annotated fields in [`ReportQueryHandler._order_by`](../../../koku/api/report/queries.py) (`numeric_ordering` includes `usage_efficiency` and `wasted_cost`).

---

## Example response fragments (implemented shape)

**`total` (after `_format_query_response`):**

```json
{
  "total": {
    "total_score": {
      "usage_efficiency_percent": 60,
      "wasted_cost": {
        "value": "402.81",
        "units": "USD"
      }
    }
  }
}
```

When scores are disabled, `"total_score": {}`.

**Data row (leaf object after grouping/transform):** same inner structure under **`score`** (not `total_score`):

```json
{
  "score": {
    "usage_efficiency_percent": 60,
    "wasted_cost": {
      "value": "402.81",
      "units": "USD"
    }
  }
}
```

**Naming note:** The early PRD example used `usage_efficiency` for the integer percent field; the shipped API uses **`usage_efficiency_percent`**.

---

## Provenance of each value

| Field | Computed where | Grain | Notes |
|-------|---------------|-------|-------|
| `usage_efficiency_percent` | API query time (ORM `Sum`) | query result grain | Always exact — simple ratio of additive quantities |
| `wasted_cpu_cost` on LIDS | `aggregate_rates_to_daily_summary.sql` Phase 2 | per LIDS cost-model row (label-set / node / namespace / day) | Exact for effective-usage metrics; approximation for usage/request metrics when pods share a label hash |
| `wasted_memory_cost` on LIDS | Same | Same | Same |
| `wasted_cpu_cost` on summary tables | UI summary SQL (`SUM` of LIDS values) | per summary row (cluster / namespace / node) | Inherits accuracy from LIDS grain |

---

## Complementary metrics (not implemented)

| Metric | Status |
|--------|--------|
| Waste score `max(100 - efficiency, 0)` | Not exposed as its own field; wasted cost follows the formula above. |
| Idle / signed unused | Backlog; see README IQ-3. |
| Cost efficiency / overhead scores | Backlog. |

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-04-16 | Initial formulas; illustrative JSON; fleet and wasted-cost options. |
| 2026-04-17 | Aligned with implementation: `_efficiency_annotations`, `_pack_score`, `total_score` vs `score`, `request=0` → 0, wasted cost formula and cost basis. |
| 2026-05-28 | Rewrote wasted cost section: formula is pre-computed in pipeline SQL at LIDS-row grain using `effective_hours` (not ORM at query time); added Phase 1 metrics table, query table selection views dict, ORM annotation snippets, `should_compute` guard code, accuracy worked example (Pod A/B), and provenance table. Removed dependency on `efficiency-scores-current-state.md`. |
