# Efficiency scores — formulas and API data contract

Companion to [README.md](./README.md). Optimized for **implementers and AI agents**: precise math, edge cases, and response shape **without** duplicating large sections of code.

---

## Canonical data fields (CPU / memory)

Aggregates today are defined on **`OCPUsageLineItemDailySummary`** in [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py):

| Metric | ORM / model fields (hours) |
|--------|----------------------------|
| CPU usage | `pod_usage_cpu_core_hours` |
| CPU request | `pod_request_cpu_core_hours` |
| Memory usage | `pod_usage_memory_gigabyte_hours` |
| Memory request | `pod_request_memory_gigabyte_hours` |

**Units in API responses** for existing compute/memory reports follow provider map / pack definitions (Core-Hours, GB-Hours, etc.). New fields should **reuse the same units** for `usage` and `request` objects.

---

## Must-have: usage efficiency (CPU and memory separately)

### Definition

For each resource dimension **R** in {`cpu`, `memory`}:

**`usage_efficiency_ratio`**

| Condition | Value |
|-----------|--------|
| `request > 0` | `usage / request` |
| `request == 0` | `null` or sentinel (**TBD** in OpenAPI) |

**API value (product):** round to **nearest whole percent**:

`usage_efficiency = round(100 * usage_efficiency_ratio)`

(Implement as `round()` in Python or `ROUND()` in SQL; confirm half-up vs banker's rounding for tests.)

**Examples** (same as product table): usage 5 / request 100 → **5**; 80 / 100 → **80**; 110 / 100 → **110** (over-requested or bursty usage — **do not clamp** to 100 unless PM explicitly changes UX).

### Implementation note for agents

- Prefer **database-side** rounding only if it matches PostgreSQL `ROUND` semantics for halves; otherwise compute in Python from aggregated decimals to match API tests.
- **`request = 0`:** document behavior explicitly in OpenAPI (e.g. omit score, or return `null`, or `0` with a flag). **Do not** divide by zero. Align with UX for “no request configured.”

---

## Transitional: “waste score” vs wasted cost

Product evolution:

1. **Waste score (percentage headroom):**
   `waste_score = max(100 - usage_efficiency, 0)`
   This **caps** at 100 and does not represent over-100% usage efficiency.

2. **Wasted cost (currency):**
   “We just use the percentage to calculate the wasted cost” — **not fully specified**. Reasonable **options** to resolve with PM/finance:

   | Option | Sketch | Pros / cons |
   |--------|--------|----------------|
   A | `wasted_cost = cost_total * (max(100 - usage_efficiency, 0) / 100)` | Simple; ignores usage > 100% for waste |
   B | `wasted_cost = (request - usage)_positive * blended_rate` | Needs rate; ties to cost model |
   C | Allocate **supplementary** CPU/memory cost by unused request share | Closer to economics; more complex |

**Agent rule:** implement **A** only if PM + engineering sign off on cost basis (`cost_total` vs infra vs supp — see `cpu` / `memory` keys `cost_total`, `cost_usage`, etc. in [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py)). Otherwise return **`wasted_cost: null`** and ship usage efficiency only.

---

## Complementary metrics (product backlog)

These are **not** locked for v1; keep names out of public API until IQ cleared.

| Metric | Direction “better” | Formula sketch | Notes |
|--------|---------------------|----------------|-------|
| Idle / request efficiency | Lower (product: may go negative) | Idle = **request − usage** (signed); score TBD | Conflicts with [`calculate_unused`](../../../koku/api/report/ocp/capacity/cluster_capacity.py) which uses `max(request - usage, 0)` for `request_unused` |
| Cost efficiency | Higher | e.g. usage_value / cost — **TBD** | |
| Overhead vs capacity | TBD | **TBD** | UX: confirm higher-vs-lower framing |

---

## Fleet aggregation

When `group_by` does not include `cluster` (or explicit “all clusters” / dashboard total):

- **Option 1 — ratio of sums:**
  `round(100 * sum(usage) / sum(request))`
  Standard for capacity-style metrics.

- **Option 2 — sum of cluster scores:**
  `sum(usage_efficiency_c)` for each cluster _c_
  Matches literal product wording but **is not** a percentage and is biased by cluster sizing.

**Agent rule:** blocked until **IQ-1** in README is resolved; document chosen rule in OpenAPI.

---

## Example response fragment (illustrative — not implemented)

Product example shape for **one** dimension (CPU) on a grouped row:

```json
{
  "usage": {
    "value": 60,
    "units": "Core-Hours"
  },
  "request": {
    "value": 100,
    "units": "Core-Hours",
    "unused": 40
  },
  "score": {
    "usage_efficiency": 60,
    "wasted_cost": 402.81
  }
}
```

**Corrections agents should apply:**

- If `unused` means **idle capacity** in the sense **request − usage**, then for usage 60 and request 100, **`unused` should be 40**, not 100 (likely a typo in the brief).
- **`usage_efficiency`:** product shows `60.00`; spec also says round to whole number — **use integer in JSON** or document fixed decimals; pick one and test.

**Parallel structure for memory:** duplicate the block with memory units and `pod_usage_memory_gigabyte_hours` / `pod_request_memory_gigabyte_hours`.

---

## Filters and group_by (product)

| Capability | Keys (align with existing OCP API) |
|------------|-------------------------------------|
| group_by | `cluster`, `node`, `project` (→ `namespace` in DB) |
| filter | `cluster`, `node`, `project` |

See [`OCPProviderMap`](../../../koku/api/report/ocp/provider_map.py) `filters` and `group_by_options` for exact field names and `icontains` vs `exact` behavior.

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-04-16 | Initial formulas; example JSON; fleet and wasted-cost options; plain Markdown formulas (no LaTeX) for broad preview support. |
