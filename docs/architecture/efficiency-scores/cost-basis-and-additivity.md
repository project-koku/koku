# Wasted cost — cost basis and cross-report additivity

Companion to [README.md](./README.md) and [formulas-and-data-contract.md](./formulas-and-data-contract.md). Describes a **structural** property of the current implementation: how **`cost_total`** feeds **`wasted_cost`**, and why **summing** wasted cost from the CPU and memory endpoints can **misrepresent** “total” waste in FinOps terms.

This document **does not** change code; it encodes a known product/UX issue for builders and PM.

---

## Scope of the cost basis (implemented)

For **`cpu`** and **`memory`**, the efficiency annotations use the same **cost** expression that backs each report’s **`cost_total`**. In [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py):

| Report | `wasted_cost` and `cost_total` share this expression |
|--------|------------------------------------------------------|
| `cpu` | `cloud_infrastructure_cost + markup_cost + cost_model_cpu_cost` |
| `memory` | `cloud_infrastructure_cost + markup_cost + cost_model_memory_cost` |

So for each line item, **infrastructure and markup** appear in **both** dimensions. Only the **`cost_model_*`** component is **CPU-specific vs memory-specific** in the additive sense (two different fields on the same rows).

Waste is then:

`wasted_cost = max(cost_total_expr × (1 - usage / request), 0)` (see [formulas-and-data-contract.md](./formulas-and-data-contract.md) for the full ORM expression and rounding).

---

## Illustrative numbers (toy model)

To reason about the user’s scenarios, treat **headline** `cost_total` as **\$100** in **both** endpoints (same time range and filters) when **`cloud_infrastructure` + `markup`** dominates the row and **cost model splits** are small or zero—i.e. both reports’ totals track the same shared dollars.

- **A — CPU 50% efficient, memory 100% efficient**
  - CPU: waste ≈ \$100 × (1 − 0.5) = **\$50**.
  - Memory: waste ≈ \$100 × (1 − 1.0) = **\$0**.
  - This is **consistent** with a single “full” cost base on each report; there is no contradiction.

- **B — CPU 50% efficient, memory 50% efficient**
  - CPU: **\$50**; Memory: **\$50** if the same full **\$100** is used in each.
  - If someone **adds** those two: **\$50 + \$50 = \$100** “total waste” from one **\$100** cost base, the result **double-counts** the shared **infrastructure + markup** (and any portion of `cost_total` that is not dimension-specific) when interpreted as a single system-wide “wasted dollars” number.

**Important:** The API does not promise that **`wasted_cost` (cpu) + `wasted_cost` (memory)`** equals a well-defined “pod waste” for the same `cost_total` in both places. The implementation defines waste **per report dimension** against a **per-dimension** `cost_total` that **repeats** shared cost components.

---

## Why this happens (engineering framing)

- **Wasted cost** is **dimensional** (CPU or memory) against **usage/request hours** for that dimension, but the **dollar** multiplier is **not** a partition of infra/markup into “CPU’s share” vs “memory’s share” of the same line—unless cost model and processing already encoded such a split in **`cloud_infrastructure_cost`** and **`markup_cost`** in a way that is exclusive per dimension, which the provider map’s additive layout does not assume for those two terms.

- Each endpoint remains internally consistent: **`cost_total`**, **usage efficiency**, and **`wasted_cost`** for that request use a **coherent** basis. The issue is **cross-dimension additivity** for people who expect to **stack** CPU and memory waste on the same **budget line**.

---

## Implications

| Audience | Implication |
|----------|-------------|
| **UI / product** | Avoid presenting **“total wasted = CPU wasted + memory wasted”** without an explicit **allocation** story or a **different** metric. |
| **FinOps** | Treat **`wasted_cost` per report** as “waste against **this** report’s `cost_total` and **this** request/usage,” not a partition of a single shared pool unless product defines one. |
| **Builders** | Any “fix” needs a **new business rule** (e.g. allocate `cloud_infrastructure` + `markup` by request ratio, or restrict waste to `cost_model_*` only, or a new combined response)—out of scope for this doc. |

---

## Tracked in the hub: IQ-7 (see [README.md](./README.md))

Cross-report **additivity and allocation of shared cost** is an open **product/engineering** decision, not a bug in the `max(cost × (1 - u/r),0)` line. For candidate resolutions (disclosure, allocation, dimension-scoped waste, combined metric, bounds, upstream split), see [iq-7-solution-options.md](./iq-7-solution-options.md).

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-04-23 | New doc: shared `cloud_infrastructure` + `markup` in both `cpu` and `memory` `cost_total` / `wasted_cost` basis; A/B examples; non-additive sum warning. |
