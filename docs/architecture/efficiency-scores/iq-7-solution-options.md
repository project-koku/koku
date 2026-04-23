# IQ-7 — Cross-dimension additivity of `wasted_cost` (solution options)

Companion to [README.md](./README.md) and [cost-basis-and-additivity.md](./cost-basis-and-additivity.md). Documents **product/engineering** options for resolving [IQ-7 in the hub](./README.md#open-questions--backlog-product-or-future-engineering): the fact that **CPU and memory** efficiency both multiply waste by a **`cost_total`** that includes the **full** line `cloud_infrastructure_cost + markup_cost` (plus dimension-specific `cost_model_*_cost`), so **summing** `wasted_cost` from `/reports/openshift/compute/` and `/reports/openshift/memory/` is **not** a defined “total” waste in dollars unless a **separate** rule is adopted.

**Status:** None of the options below are selected; this file is a decision aid. When product chooses, update [README.md](./README.md) (open vs resolved IQ-7), [formulas-and-data-contract.md](./formulas-and-data-contract.md), and [cost-basis-and-additivity.md](./cost-basis-and-additivity.md) to match the shipped behavior.

---

## Ground truth (as implemented)

- Waste uses `max(cost_total × (1 − usage / request), 0)`; see [formulas-and-data-contract.md](./formulas-and-data-contract.md).
- `cost_total` for **`cpu`**: `cloud_infrastructure_cost + markup_cost + cost_model_cpu_cost`.
- `cost_total` for **`memory`**: `cloud_infrastructure_cost + markup_cost + cost_model_memory_cost`.
- Annotations: [`OCPProviderMap._efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py) with those expressions for `cpu` and `memory` in [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py).

**Related columns already on the same line items (not used for `wasted_cost` today):** The provider map’s **`cpu`** / **`memory`** report definitions expose a breakdown where **`infra_raw`** is the full line `cloud_infrastructure_cost` and **`infra_usage`** is `cost_model_cpu_infrastructure_cost` or `cost_model_memory_infrastructure_cost`, while **`cost_total`** for inventory (and for efficiency) still includes **full** `cloud_infrastructure_cost + markup_cost` plus the applicable `cost_model_*_cost`. Any solution that reuses a **partition** of shared dollars must be **explicitly** specified by product—nothing in code today allocates line-level `cloud_infrastructure` or `markup` between CPU and memory for the waste multiplier.

---

## Option A — Disclosure only (“do not add”)

| | |
|---|--|
| **Idea** | Do **not** present `wasted_cost` (compute) + `wasted_cost` (memory) as a single reconciled “total” waste. Label each as waste against **that** report’s `cost_total` and usage/request. |
| **System impact** | **Product + UI + docs** (copy, tooltips, OpenAPI wording). **No** backend change. |
| **Tradeoffs** | Fast; **honest**. No **single** dollar “total pod waste” from two endpoints. |

---

## Option B — Allocate shared dollars between CPU and memory

| | |
|---|--|
| **Idea** | Partition **`cloud_infrastructure_cost + markup_cost`** (per aggregated row or fleet) into CPU vs memory with weights `w_cpu + w_mem = 1`, then use **`allocated_shared + cost_model_*`** (or an equivalent) as the dollar multiplier in each report’s `wasted_cost` so that **defined** sums are possible. |
| **Example weighting rules** (illustrative only) | (1) Proportional to **cost** — e.g. `w_cpu = cost_model_cpu / (cost_model_cpu + cost_model_memory)` when the denominator is non-zero; (2) other **$**-based rules from cost management; (3) fixed **50/50** (rarely defensible, but simple). **Core-hours vs GiB-hours** are not natively in the same unit; **$**-based or cost-model–based splits avoid mixing resource units. |
| **System impact** | New expressions in [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py) and possibly aligned **`cost_total` semantics** for the efficiency story; tests under [`koku/api/report/test/ocp/`](../../../koku/api/report/test/ocp/); **documentation** updates. Still **ORM on tenant** [`OCPUsageLineItemDailySummary`](../../../koku/reporting/models.py) under existing patterns unless a different architecture is chosen. |
| **Tradeoffs** | Sums can become **internally** consistent with one allocation rule. **Wrong** rule misleads FinOps; **product** must own the rule. |

---

## Option C — Wasted dollars on dimension-scoped cost only

| | |
|---|--|
| **Idea** | Change the **`wasted_cost` multiplier** to use **only** dimension-scoped cost (e.g. `cost_model_cpu_cost` or `cost_model_memory_cost` only, or a narrower combination of `cost_model_*_infrastructure` + supplementary, **without** full line `cloud_infrastructure` + `markup`). |
| **System impact** | Change `cost_total_expr` passed into [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py) for `cpu` and `memory`; may **diverge** from headline **`cost_total`** on the same report unless product also redefines displayed totals; **docs** + **UI**. |
| **Tradeoffs** | **Additivity** of CPU + memory may improve if those components **partition** the attributed dollars. If most spend remains on **unallocated** line `cloud_infrastructure`, “waste $” can **understate** financial exposure unless product explains the metric. |

---

## Option D — One combined “pod” or “workload” waste metric

| | |
|---|--|
| **Idea** | Expose a **single** `wasted_cost` (or `combined_wasted_cost`) from **one** formula and one pass over the data (e.g. one shared cost pool and a **joint** efficiency rule, such as a conservative `shared × (1 − f(ε_cpu, ε_mem))` where `f` is min, max, or another agreed function). |
| **System impact** | **API** shape (new field, query flag, or resource); [`OCPReportQueryHandler`](../../../koku/api/report/ocp/query_handler.py), [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py), **serializers**; may require **aggregating** both usage/request series in one request. **Multi-tenancy** unchanged (`tenant_context`). |
| **Tradeoffs** | One **defensible** number for executive views; the **joint** function is a **new** product definition, not a restatement of per-dimension `wasted_cost` today. |

---

## Option E — Bounds or non-additive presentation

| | |
|---|--|
| **Idea** | Show **max** of the two, a **range**, or “at least / at most” against the shared pool, instead of a sum. |
| **System impact** | Mostly **UI**; API might expose optional read-only **bounds** if useful. |
| **Tradeoffs** | Avoids false precision; can feel **weak** for a single headline KPI. |

---

## Option F — Upstream partition of `cloud_infrastructure` / `markup`

| | |
|---|--|
| **Idea** | If ingestion or cost model **splits** line-level infrastructure and markup into **exclusive** CPU vs memory (or per-resource) fields on each line item, then each report’s `cost_total` could be **naturally** disjoint. |
| **System impact** | **Pipeline / OCP / cost model** and possibly new or changed columns; **largest** scope. Provider map and efficiency expressions would **follow** the new contract. |
| **Tradeoffs** | Aligns **all** of reporting, not just efficiency, with a **single** data model; **long** lead time. |

---

## Suggested decision order

1. Confirm whether the business needs **(a)** a honest non-additive story, **(b)** an **allocatable** sum, or **(c)** a **new** single combined metric.
2. If **(b)**: product selects **B** (allocation) vs **C** (scope waste to cost-model slices) vs **F** (structural data fix).
3. If **(c)**: specify **D** in detail and deprecate or clarify the relationship to per-dimension `wasted_cost`.
4. If **(a)**: **A** with optional **E** for advanced UX.

**Owner for the numeric/FinOps rule:** Product / cost management, with engineering to implement and to verify **multi-tenancy** and test coverage on tenant [`OCPUsageLineItemDailySummary`](../../../koku/reporting/models.py).

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-04-23 | New doc: IQ-7 solution options A–F, grounded in `OCPProviderMap` and hub links. |
