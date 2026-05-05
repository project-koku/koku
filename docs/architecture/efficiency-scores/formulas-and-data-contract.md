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
| **Percent** | `Round(ratio * 100)` as **integer** (Django `Round` + `IntegerField` in [`_efficiency_annotations_row_waste_sum`](../../../koku/api/report/ocp/provider_map.py)). |
| **Null / zero request** | `Coalesce(..., 0)` → API exposes **`0`** when the ratio is null (including **`request_sum == 0`**). |

So **`usage_efficiency_percent` can exceed 100** when usage exceeds request over the aggregated rows (not clamped).

### API field name

Response shaping is done in [`OCPReportQueryHandler._pack_score`](../../../koku/api/report/ocp/query_handler.py): the internal annotation `usage_efficiency` is exposed as **`usage_efficiency_percent`**.

---

## Wasted cost (`wasted_cost`)

### Definition (implemented) — sum of per-row waste

[`_efficiency_annotations_row_waste_sum`](../../../koku/api/report/ocp/provider_map.py) computes **`wasted_cost`** as **`Sum(per_row_waste)`** over the same rows that feed the report (fleet aggregate or each `group_by` bucket). **`usage_efficiency_percent`** in that helper remains **ratio-of-sums** (see above); the two fields **can diverge** by design.

Per row *i*, with coalesced usage **u_i**, request **r_i**, and row cost **c_i** (same linear components as aggregate **`cost_total`**, without wrapping **`Sum`**):

- **c_i** from [`_per_row_cost_cpu_expr`](../../../koku/api/report/ocp/provider_map.py) (**`cpu`**) or [`_per_row_cost_memory_expr`](../../../koku/api/report/ocp/provider_map.py) (**`memory`**): infra raw + markup (each × `infra_exchange_rate`) + cost-model CPU or memory (× `exchange_rate`), matching the inventory **`cost_total`** basis at row grain.
- **waste_i** = `Coalesce(Greatest(c_i * (1 - u_i / NullIf(r_i, 0)), 0), 0)` — `NullIf` avoids divide-by-zero; **`r_i == 0`** → that row contributes **0**; over-requested rows contribute **0** waste.

**`wasted_cost`** = **Σ waste_i** (ORM **`Sum(per_row_waste)`**), with outer **`Coalesce(..., 0)`** when the aggregate is null.

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

- **Total row:** `query.aggregate(**aggregates)` applies **`usage_efficiency`** as **one ratio of sums** over the **entire filtered queryset**, and **`wasted_cost`** as the **sum of per-row waste** over those same rows (not an average of per-cluster percentages, and not fleet `cost_total × (1 - U/R)`).
- **Grouped rows:** Each group gets its own **`usage_sum`**, **`request_sum`**, and its own **`Sum(per_row_waste)`** from `values(...).annotate(...)`.

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
| Waste score `max(100 - efficiency, 0)` | Not exposed as its own field; **`wasted_cost`** is sum-of-row clamped waste (not that scalar). |
| Idle / signed unused | Backlog; see README IQ-3. |
| Cost efficiency / overhead scores | Backlog. |

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-04-16 | Initial formulas; illustrative JSON; fleet and wasted-cost options. |
| 2026-04-17 | Aligned with implementation: `_pack_score`, `total_score` vs `score`, `request=0` → 0, wasted cost formula and cost basis. |
| 2026-05-05 | **`wasted_cost`:** `_efficiency_annotations_row_waste_sum`, per-row cost helpers, **`Sum`** of clamped row waste; **`usage_efficiency_percent`** unchanged (ratio-of-sums). |
