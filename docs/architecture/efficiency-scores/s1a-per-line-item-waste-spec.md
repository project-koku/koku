# Spec: S1-a — Per-line-item waste, then `Sum` (current OCP compute/memory flow)

**Status:** Draft for engineering
**Parent analysis:** [solution-options-and-limitations.md](./solution-options-and-limitations.md) (S1-a, S2-a)
**Math contract (today):** [formulas-and-data-contract.md](./formulas-and-data-contract.md)
**Hub:** [README.md](./README.md)

---

## 1. Objective

Change **`wasted_cost`** on OpenShift **`cpu`** and **`memory`** inventory reports so it matches **bottom-up “sum of opportunities”**: for each qualifying row in the report queryset, compute waste from **that row’s** usage, request, and dimension-scoped cost, clamp at zero, then **`Sum`** those values for the fleet total and for each **`group_by`** bucket.

**Unchanged unless product decides otherwise (IQ-8):**
- **`usage_efficiency_percent`** stays **ratio-of-sums** (aggregate `usage_sum / request_sum`, rounded), as today.
- **`should_compute`** gates, response shape (`total_score` / `score`), tenancy (`tenant_context`), and **Problem 3** (CPU + memory double-count of shared infra if users sum endpoints) are **out of scope** for this spec unless explicitly pulled in.

---

## 2. Semantics

### 2.1 Row grain

**Assumption (pending IQ-7):** One **`OCPUsageLineItemDailySummary`** row after the report’s filters is the unit of “line item” for S1-a. Product confirms this matches FinOps examples (pod vs coarser aggregation).

If IQ-7 concludes a different grain, this spec’s ORM expressions must be applied at that grain (e.g. subquery or pipeline pre-aggregation) before **`Sum`**; the **formula** below still applies per grain unit.

### 2.2 Per-row fields (mirror today’s `cost_total` basis)

For each report **`report_type`**:

| Dimension | Row usage (hours) | Row request (hours) | Row `cost_total` (same components as [formulas-and-data-contract.md](./formulas-and-data-contract.md)) |
|-----------|-------------------|---------------------|--------------------------------------------------------------------------------------------------------|
| **cpu** | `pod_usage_cpu_core_hours` | `pod_request_cpu_core_hours` | `cloud_infrastructure_cost` + `markup_cost` + **`cost_model_cpu_cost`** — expressed **per row** (see §3.2) |
| **memory** | `pod_usage_memory_gigabyte_hours` | `pod_request_memory_gigabyte_hours` | `cloud_infrastructure_cost` + `markup_cost` + **`cost_model_memory_cost`** — **per row** |

Use **`Coalesce(..., 0)`** on usage and request consistently with [`_cpu_usage_sum`](../../../koku/api/report/ocp/provider_map.py) / [`_memory_request_sum`](../../../koku/api/report/ocp/provider_map.py).

### 2.3 Per-row waste expression

Let **c_i**, **u_i**, **r_i** be row cost, usage, and request after coalescing. Per row:

```text
waste_i = max( c_i * (1 - u_i / NULLIF(r_i, 0)), 0 )
```

(`NULLIF` matches SQL / ORM: divide-by-zero avoided; when the ratio is null, the implementation **`Coalesce`s** the clamped term to **0**, same as [formulas-and-data-contract.md](./formulas-and-data-contract.md).)

**Aggregate** `wasted_cost` for the bucket:

```text
wasted_cost = sum over i of waste_i
```

— over the filtered set (fleet **`aggregate`**) or within each **`values(...).annotate(...)`** group.

This simultaneously addresses **Problem 1 (aggregation bias)** and **Problem 2 (over-utilization masking)** as described in [solution-options-and-limitations.md](./solution-options-and-limitations.md).

---

## 3. Technical design (current stack)

### 3.1 Touch points

| Layer | File | Change |
|-------|------|--------|
| Aggregates & grouped annotations | [`koku/api/report/ocp/provider_map.py`](../../../koku/api/report/ocp/provider_map.py) | Replace pooled **`wasted_cost`** in **`_efficiency_annotations`** usage for **`cpu`** / **`memory`** with **`Sum(per_row_waste_expr)`**, or add a parallel helper (e.g. `_efficiency_annotations_row_waste_sum`) and wire it into **`aggregates`** and **`annotations`** for those report types only. |
| Response packing | [`koku/api/report/ocp/query_handler.py`](../../../koku/api/report/ocp/query_handler.py) | No shape change; still maps internal **`wasted_cost`** to **`wasted_cost.value`**. |
| Ordering | [`koku/api/report/queries.py`](../../../koku/api/report/queries.py) (`_order_by`) | **`order_by[wasted_cost]`** must sort by the **new** annotated `Sum` (same alias **`wasted_cost`**). Confirm in-memory ordering still sees the annotation after queryset evaluation. |
| Tests | [`koku/api/report/test/ocp/test_ocp_query_handler.py`](../../../koku/api/report/test/ocp/test_ocp_query_handler.py) and IQE | Update expectations where fleet/group totals used pooled math; add regression cases matching brief examples / `test_api_ocp_ingest_efficiency_*` scenarios. |

**Non-goals for this change:** `masu/database/sql/`, `trino_sql/`, Celery tasks — S1-a can remain **ORM-only** on tenant summaries (same as today).

### 3.2 Row-level `cost_total` expression

Today, [`cloud_infrastructure_cost`](../../../koku/api/report/ocp/provider_map.py) and [`markup_cost`](../../../koku/api/report/ocp/provider_map.py) are **`Sum(...)`** over row expressions. For per-row waste, introduce **non-aggregated** equivalents (same multipliers and fields, without **`Sum`**), e.g.:

- Row infra: `Coalesce(F("infrastructure_raw_cost"), 0) * Coalesce(F("infra_exchange_rate"), 1)`
- Row markup: `Coalesce(F("infrastructure_markup_cost"), 0) * Coalesce(F("infra_exchange_rate"), 1)`
- Row CPU cost model: `Coalesce(F("cost_model_cpu_cost"), 0) * Coalesce(F("exchange_rate"), 1)` (memory: `cost_model_memory_cost`)

**Sum** of these row terms must equal the existing aggregated **`cost_total`** for the same queryset (sanity check / test).

Compose **`per_row_cost_cpu`** / **`per_row_cost_memory`** as the same linear combinations used in **`cost_total`** for **`cpu`** and **`memory`** blocks (lines ~430 and ~581 in `provider_map.py`).

### 3.3 ORM pattern

Conceptually:

```text
per_row_waste = Coalesce(
    Greatest(
        per_row_cost * (1 - per_row_usage / NullIf(per_row_request, 0)),
        Value(0),
    ),
    Value(0),
)
wasted_cost = Sum(per_row_waste)   # in aggregate() or grouped annotate()
```

Reuse the same **`DecimalField`** precision patterns as [`_efficiency_annotations`](../../../koku/api/report/ocp/provider_map.py) to avoid silent type widening issues.

**`usage_efficiency`:** Keep current implementation (aggregated **`usage_sum_prop`** / **`request_sum_prop`**) so the percent column does not change unless IQ-8 chooses alignment.

---

## 4. Product / API decisions (blockers or follow-ups)

| ID | Question | Impact if unresolved |
|----|----------|----------------------|
| **IQ-7** | Confirm **`OCPUsageLineItemDailySummary`** row = intended “workload” unit | Wrong grain → wrong customer narrative |
| **IQ-8** | OK for **`usage_efficiency_percent`** (pooled ratio) and **`wasted_cost`** (sum of row waste) to **diverge**? | Doc + UI copy; possible future second field if both metrics needed (IQ-9) |
| **IQ-9** | If customers need **both** pooled and opportunity waste, names and defaults | New or renamed JSON fields; OpenAPI |

Until IQ-8 is explicit, document in release notes that **efficiency %** is still **fleet/group utilization** (ratio of sums), while **wasted cost** is **additive opportunity** (sum of clamped row waste).

---

## 5. Acceptance criteria

1. **Numeric:** For the worked examples in [solution-options-and-limitations.md](./solution-options-and-limitations.md) (Problems 1 and 2), API **`wasted_cost`** for the same filtered data matches **sum of per-row clamped waste**, not pooled **`cost × (1 - U/R)`**.
2. **`group_by`:** Project, cluster, node, and other supported inventory groupings return **`wasted_cost`** = **`Sum`** of row waste **within that group**; fleet total = **`Sum`** over all filtered rows.
3. **Edge cases:** **`request_sum == 0`** at row level → that row contributes **0** waste; over-utilized rows contribute **0**; under-utilized rows still contribute positive amounts when the group’s pooled ratio would have zeroed pooled waste.
4. **Ordering:** **`order_by[wasted_cost]`** orders by the new aggregate.
5. **Tenancy:** No regression to **`tenant_context`** isolation.
6. **Performance:** Run **`EXPLAIN (ANALYZE)`** (or equivalent) on representative tenant/date windows; record delta vs current pooled expression. If unacceptable, follow-up task: partial indexes, materialized subquery, or precomputed column (out of scope here).

---

## 6. Test plan (minimum)

- **Unit / handler:** Extend [`test_ocp_query_handler`](../../../koku/api/report/test/ocp/test_ocp_query_handler.py) with small fixtures: two rows in one cluster, costs and usage/request chosen so pooled waste ≠ sum of row waste; assert **`wasted_cost`** equals sum of row formula.
- **Over-utilization mix:** One under-, one over-provisioned row; assert non-zero **`wasted_cost`** when pooled would be zero.
- **Regression:** Existing tests that hard-code old **`wasted_cost`** values must be updated.
- **Ordering:** One test that **`order_by[wasted_cost]`** returns rows in descending **`wasted_cost`** under the new definition.

---

## 7. Documentation updates (post-merge)

- [formulas-and-data-contract.md](./formulas-and-data-contract.md): **`wasted_cost`** section — replace pooled definition with **sum of row-level clamped waste**; note **`usage_efficiency_percent`** unchanged (if IQ-8 confirms).
- [README.md](./README.md): Resolved / backlog table — note IQ-2 superseded or narrowed for **`wasted_cost`** only.
- [solution-options-and-limitations.md](./solution-options-and-limitations.md): Optional one-line “**Implemented:** S1-a as of …” when shipped.

---

## 8. Changelog

| Date | Summary |
|------|---------|
| 2026-04-29 | Initial spec from S1-a row in solution-options-and-limitations. |
