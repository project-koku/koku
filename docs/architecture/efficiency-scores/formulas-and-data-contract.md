# Efficiency scores — formulas and API data contract

Companion to [README.md](./README.md). Describes the **implemented** backend behavior for CPU and memory **usage efficiency** and **wasted cost** on OpenShift compute/memory reports.

---

## Canonical data fields (CPU / memory)

Aggregates are defined on **`OCPUsageLineItemDailySummary`** in [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py) for `report_type` **`cpu`** and **`memory`**.

| Metric | Model fields (hours) |
|--------|----------------------|
| CPU usage | `pod_usage_cpu_core_hours` |
| CPU request | `pod_request_cpu_core_hours` |
| Memory usage | `pod_usage_memory_gigabyte_hours` |
| Memory request | `pod_request_memory_gigabyte_hours` |

Sums use `Coalesce(..., 0)` via helpers such as [`_cpu_usage_sum`](../../../koku/api/report/ocp/provider_map.py) / [`_memory_request_sum`](../../../koku/api/report/ocp/provider_map.py).

---

## Usage efficiency (`usage_efficiency_percent`)

### Definition (implemented)

Let **`usage_sum`** and **`request_sum`** be the **Sum** expressions for the appropriate resource for the current aggregate (total or group).

| Expression | Meaning |
|------------|---------|
| Ratio | `usage_sum / NULLIF(request_sum, 0)` — avoids division by zero. |
| **Percent** | `Round(ratio * 100)` as **integer** (Django `Round` + `IntegerField` in [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py)). |
| **Null / zero request** | `Coalesce(..., 0)` → API exposes **`0`** when the ratio is null (including **`request_sum == 0`**). |

So **`usage_efficiency_percent` can exceed 100** when usage exceeds request over the aggregated rows (not clamped).

### API field name

Response shaping is done in [`OCPReportQueryHandler._pack_score`](../../../koku/api/report/ocp/query_handler.py): the internal annotation `usage_efficiency` is exposed as **`usage_efficiency_percent`**.

---

## Wasted cost (`wasted_cost`)

### Definition (implemented)

Uses the same **`usage_sum`**, **`request_sum`**, and a **`cost_total_expr`** passed into [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py):

`wasted_cost = Coalesce(Greatest(cost_total * (1 - usage_sum / NullIf(request_sum, 0)), 0), 0)` (ORM/SQL expression; `NullIf` avoids divide-by-zero).

- **`cost_total`** for **`cpu`**: `cloud_infrastructure_cost + markup_cost + cost_model_cpu_cost` (same components as the `cost_total` aggregate for CPU inventory).
- **`cost_total`** for **`memory`**: `cloud_infrastructure_cost + markup_cost + cost_model_memory_cost`.

So this is **not** “waste percent × arbitrary headline cost” from a different column — it tracks the **`cost_total` expression for that dimension** in the provider map.

Because **`cloud_infrastructure_cost`** and **`markup_cost`** are included in **both** the CPU and memory **`cost_total`** expressions, the **dollar** basis is **overlapping** between reports. **Do not** add **`wasted_cost`** from `compute` and `memory` and treat the sum as a single “total” waste for the same workload without an allocation model—see [cost-basis-and-additivity.md](./cost-basis-and-additivity.md) and [README](./README.md) **IQ-7**.

When **`request_sum`** is zero, the ratio is null; the expression yields null and **`Coalesce`** forces **`wasted_cost`** to **decimal 0**.

### API shape

```json
"wasted_cost": {
  "value": "<Decimal>",
  "units": "<user currency from report context>"
}
```

`units` comes from the handler’s currency (`self.currency` in [`_pack_score`](../../../koku/api/report/ocp/query_handler.py)).

---

## Fleet vs grouped rows

- **Total row:** `query.aggregate(**aggregates)` applies the same **`usage_efficiency`** and **`wasted_cost`** definitions over the **entire filtered queryset** — i.e. one combined ratio and one wasted-cost expression for the fleet (not an average of per-cluster percentages).
- **Grouped rows:** Each group gets its own **`usage_sum`**, **`request_sum`**, and **`cost_total`** slice from `values(...).annotate(...)`.

---

## When scores are absent or empty

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
| 2026-04-23 | Cross-dimension: pointer to [cost-basis-and-additivity.md](./cost-basis-and-additivity.md) — shared infra+markup in each report’s `cost_total`; non-additive sum of `wasted_cost` across reports. |
