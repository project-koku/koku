# Cost Breakdown for OpenShift Price List Costs

Technical design for per-rate cost breakdowns in the OpenShift cost
management pipeline, enabling users to see itemized costs (e.g.,
"OpenShift Subscriptions," "GuestOS Subscriptions," "Operation") instead
of aggregated totals.

**Jira Epic**: [COST-7249](https://redhat.atlassian.net/browse/COST-7249)
**Related Epics**: [COST-2105](https://redhat.atlassian.net/browse/COST-2105) (custom rates), [COST-4415](https://redhat.atlassian.net/browse/COST-4415) (cloud services)
**PRD**: [PRD04 — Cost Breakdown](https://docs.google.com/document/d/1wWdrYuhNpiJPMgVdJzS6yTvCKxRZ1g5j6CLzLJjASHA/edit?tab=t.0#heading=h.sdhov05ddhog)

**Prerequisite reading**: [cost-models.md](../cost-models.md) — describes
the current cost model architecture, rate types, distribution, and data
model that this feature extends.

---

## Decisions Needed from Tech Lead

The following design decisions have been resolved by the tech lead and PM
where noted.

| # | Decision | Status | Blocking Phase | Proposal | PoC Artifact |
|---|----------|--------|---------------|----------|--------------|
| **IQ-1** | Single source of truth: RatesToUsage with aggregation to daily summary. | **RESOLVED** | ~Phase 2~ | [Details](#iq-1-aggregation-granularity-mismatch-phase-2-3) | [`poc/insert_usage_rates_to_usage.sql`](./poc/insert_usage_rates_to_usage.sql) demonstrates fine-grained GROUP BY |
| **IQ-3** | Flat-row DB storage with both flat and nested API response formats. | **RESOLVED** | ~Phase 4~ | [Details](#iq-3-breakdown-api-response-format-phase-4) | [`poc/reporting_ocp_cost_breakdown_p.sql`](./poc/reporting_ocp_cost_breakdown_p.sql) produces flat rows with path columns |
| **IQ-6** | Remove speculative `PriceList.usage_start` / `usage_end` fields (not in PRD). | **RESOLVED** | ~Phase 1~ | [Details](#iq-6-pricelistusage_startusage_end-phase-1) | — |
| **IQ-7** | `custom_name` optional with auto-generation from `description` or `metric.name`. Backward compatible. | **RESOLVED** | ~Phase 1~ | [Details](#iq-7-backward-compatibility-for-custom_name-phase-1) | [`poc/price_list_compat.py`](./poc/price_list_compat.py) validates backward-compatible format |
| **IQ-8** | `cost_type` on `OCPCostUIBreakDownP`. | **RESOLVED** | ~Phase 4~ | [Details](#iq-8-cost_type-on-ocpcostuibreakdownp-phase-4) | — |
| **IQ-9** | Distribution per-rate identity: preserve per-rate breakdown for distributed costs. | **RESOLVED** | ~Phase 4~ | Distribution rewritten to operate on per-rate `RatesToUsage` rows (Option 1). Old distribution SQL deprecated; new files read from `RatesToUsage` + daily summary usage metrics. [Details](#iq-9-distribution-per-rate-identity-gap) | [sql-pipeline.md](./sql-pipeline.md) (pipeline sketches; Option 2 back-allocation retained as fallback) |

### What the spikes resolved

Four proof-of-concept spikes were completed to reduce technical risk.
All artifacts are in [`poc/`](./poc/):

| Spike | Risk eliminated | Artifact |
|-------|----------------|----------|
| CTE + UNION ALL for RatesToUsage INSERT | IQ-2 (distribution-dependent `metric_type`), IQ-5 (SQL approach) | [`poc/insert_usage_rates_to_usage.sql`](./poc/insert_usage_rates_to_usage.sql) |
| `build_path()` CASE/WHEN SQL | IQ-4 (placeholder functions) | [`poc/reporting_ocp_cost_breakdown_p.sql`](./poc/reporting_ocp_cost_breakdown_p.sql) |
| Row-count estimation query | R3 (row explosion sizing) | [`poc/estimate_rates_to_usage_rows.sql`](./poc/estimate_rates_to_usage_rows.sql) |
| `_price_list_from_rate_table()` format compatibility | Phase 1 read-path risk | [`poc/price_list_compat.py`](./poc/price_list_compat.py) — 6/6 tests pass |

### Residual risks (process-dependent, cannot fully mitigate in design)

See [risk-register.md](./risk-register.md) for full details on all risks.

- **R6**: 25 SQL file modifications — per-file-per-PR + 8-point checklist
- **R10**: Trino dialect edge cases — requires Trino-enabled dev environment
- **R18**: Distribution SQL rewrite regression — old files preserved for rollback
- **R19**: Aggregation handling of `distributed_cost` — **open, needs tech lead input**
- **Phase 4 frontend accuracy**: `koku-ui` may change before Phase 4

---

## Open Questions — All Resolved

Previously blockers for Phase 2. All four have been resolved via source
code triage.

### OQ-1: How do the 6 CPU cost components map to named rates? — RESOLVED

Each component maps 1:1 to a distinct user-configurable rate metric in
`COST_MODEL_USAGE_RATES` (`api/metrics/constants.py`). Components 4-6
**are** independent rates — they are separate entries the user sets in
the cost model, not derived from other rates.

| # | Component | Rate metric | `metric_type` |
|---|-----------|-------------|---------------|
| 1 | Pod CPU usage | `cpu_core_usage_per_hour` | cpu |
| 2 | Pod CPU request | `cpu_core_request_per_hour` | cpu |
| 3 | Pod CPU effective usage | `cpu_core_effective_usage_per_hour` | cpu |
| 4 | Node core allocation | `node_core_cost_per_hour` | cpu |
| 5 | Cluster core allocation | `cluster_core_cost_per_hour` | cpu |
| 6 | Cluster hourly (via CTE) | `cluster_cost_per_hour` | cpu |

Memory has 4 rates (3 direct + cluster CTE), volume has 2 rates.
**Total: 12 `RatesToUsage` rows per daily summary row** when all rates
are configured. Rates set to 0 produce rows with `calculated_cost = 0`
(they can be excluded from the breakdown UI).

**SQL approach**: One CTE computes all 12 component expressions from
the same GROUP BY, then 12 INSERTs into `RatesToUsage` select one
component each. This avoids duplicating the base aggregation.

See [sql-pipeline.md § How usage_costs.sql Works Today](./sql-pipeline.md#how-usage_costssql-works-today) for the full SQL analysis.

### OQ-2: How do monthly cost rates map to `RatesToUsage` rows? — RESOLVED

`monthly_cost_cluster_and_node.sql` uses this GROUP BY:

```
GROUP BY usage_start, source_uuid, cluster_id, node, namespace,
         pod_labels, cost_category_id
```

This is **finer** than one row per `(namespace, node, usage_start)` —
`pod_labels` and `cost_category_id` can vary within the same namespace
on the same node. There are 6 monthly cost types in
`MONTHLY_COST_RATE_MAP`: Node, Node_Core_Month, Cluster, PVC, OCP_VM,
OCP_VM_CORE.

**Row count per monthly rate per month** =
`N_days × N_distinct(cluster, node, namespace, pod_labels, cost_category)`.

For `RatesToUsage`, each such row becomes one `RatesToUsage` INSERT.
The `monthly_cost_type` column (`Node`, `Cluster`, `PVC`, etc.)
serves as the `custom_name` for monthly rates.

**Rate selection**: The updater checks `_infra_rates` first, then
`_supplementary_rates`. A given monthly rate is either Infrastructure
**or** Supplementary (never both) per cost model.

### OQ-3: Aggregation validation strategy — RESOLVED

**Recommendation: Option C (regression tests).**

Source code triage confirmed that koku has **no existing infrastructure**
for dual-path or shadow-mode SQL comparison. The closest pattern is
`DataValidator` in `masu/processor/_tasks/data_validation.py`, which
validates raw usage data sums — a different concern.

Building a dual-write framework (Option A/B) would add significant
complexity for a one-time migration check. Instead:

1. **Phase 2 validation query** (`validate_rates_against_daily_summary.sql`)
   runs as a read-only `SELECT` comparing `SUM(RatesToUsage.calculated_cost)`
   against the existing daily summary `cost_model_*_cost` columns, per
   provider, per day. See [sql-pipeline.md](./sql-pipeline.md).
2. **Regression tests** with known-good cost model configurations verify
   that the aggregation step reproduces identical scalars.
3. **CI gate**: the validation query runs in integration tests to
   verify aggregation correctness.

### OQ-4: Cost category reclassification and breakdown tree — RESOLVED

**No special handling needed.** Source code confirms that reclassification
already triggers full recomputation.

`CostGroupsAddView` and `CostGroupsRemoveView` (in
`api/settings/cost_groups/view.py`) both call `_summarize_current_month()`,
which enqueues `update_summary_tables` for each affected provider. This
task chains into `update_cost_model_costs`, which re-runs the full cost
model pipeline including UI summary population.

Since `OCPCostUIBreakDownP` population will be wired into the same
summary update chain (Phase 4), any cost category reclassification will
automatically repopulate the breakdown table for the current month.
No additional trigger is required.

---

## Implementation Questions + Proposals

These were identified during a final critical review. Each represents
a design gap or assumption. For each, we propose a solution based on
koku's existing architecture and patterns. The tech lead should confirm
or override these proposals.

### IQ-1: Aggregation granularity mismatch (Phase 2-3) — RESOLVED

**Problem**: `usage_costs.sql` groups by `(pod_labels, volume_labels,
persistentvolumeclaim, cost_category_id)` — each distinct combination
gets its own daily summary row with its own costs. The original
`RatesToUsage` design did not have those columns, making
aggregation back to the daily summary impossible at the correct
granularity.

**Resolution**: Tech lead confirmed the single-source-of-truth
approach. `RatesToUsage` gains four fine-grained columns
(`pod_labels`, `volume_labels`, `persistentvolumeclaim`, `all_labels`)
to match the `usage_costs.sql` GROUP BY exactly. The aggregation step
uses DELETE + INSERT (matching `usage_costs.sql`'s existing pattern)
to populate the daily summary from `RatesToUsage`.

This means:

- `aggregate_rates_to_daily_summary.sql` is a **Phase 2 production
  artifact** — it replaces `usage_costs.sql` direct-write immediately
- `validate_rates_against_daily_summary.sql` is a **CI-only** regression
  test that verifies aggregation correctness in integration tests
- `RatesToUsage` stores per-rate costs at the same granularity as the
  daily summary — it IS the single source of truth
- There is no temporary dual-path: `usage_costs.sql` direct-write is
  replaced (not kept alongside) in Phase 2
- Phase 5 includes removing dead code from the legacy direct-write path

**New risks introduced by this approach** (captured in the
[risk register](./risk-register.md)):

- **R13**: ~~JSONB column JOINs in the aggregation SQL may be slow~~
  **MITIGATED** — `label_hash` column replaces JSONB GROUP BY/JOIN.
  See [data-model.md](./data-model.md) and [sql-pipeline.md](./sql-pipeline.md).
- **R3 update**: Fine-grained granularity increases `RatesToUsage` row
  counts beyond the original 36M/month worst-case estimate. Phase 2
  benchmarking plan has concrete acceptance criteria.

### IQ-2: `cluster_cost_per_hour` metric_type is distribution-dependent (Phase 2)

**Problem**: `cluster_cost_per_hour` contributes to
`cost_model_cpu_cost` when `distribution = 'cpu'` but to
`cost_model_memory_cost` when `distribution = 'memory'`.

**Proposal: Set `metric_type` dynamically in the SQL.**

`usage_costs.sql` already uses `{%- if distribution == 'cpu' %}`
Jinja2 conditionals for this exact rate in the `cte_node_cost` CTE.
The `RatesToUsage` INSERT should use the same pattern:

```sql
{%- if distribution == 'cpu' %}
'cpu' AS metric_type,
{%- else %}
'memory' AS metric_type,
{%- endif %}
```

`node_core_cost_per_hour` and `cluster_core_cost_per_hour` (components
4-5) always contribute to `cost_model_cpu_cost` regardless of
distribution (verified in source), so their `metric_type` is always
`'cpu'`. Only `cluster_cost_per_hour` (component 6) needs the dynamic
conditional.

### IQ-3: Breakdown API response format (Phase 4) — RESOLVED

**Problem**: The nested `breakdown` array format doesn't match koku's
standard query handler output.

**Resolution**: Tech lead confirmed flat-row DB storage with **both**
flat and nested API response formats. The UI mocks require both views.

- **Database**: `OCPCostUIBreakDownP` stores flat rows with `path`,
  `depth`, `parent_path`, `custom_name`, `cost_value`, etc.
- **Flat API response**: Standard `OCPReportQueryHandler`-style output
  with flat annotated rows grouped by date. Uses the same `provider_map`
  pattern as all other koku report endpoints.
- **Nested API response**: Built from the same flat DB rows by
  reconstructing the tree from `path`/`parent_path` server-side (or
  client-side). Controlled via `?view=tree` query parameter.

This keeps the DB layer simple (flat rows, standard indexes, standard
pagination) while serving both UI views from a single data source.

### IQ-4: `build_path()` logic (Phase 4)

**Problem**: Placeholder functions, not actual SQL.

**Proposal: CASE/WHEN expressions in the INSERT...SELECT.**

This follows the same pattern used by distribution SQL files (which
determine cost_model_rate_type via CASE) and UI summary SQL files.

```sql
-- top_category
CASE
    WHEN r.cost_category_id IS NULL THEN 'project'
    WHEN cc.name = 'Platform' THEN 'overhead'
    ELSE 'project'
END AS top_category,

-- breakdown_category
CASE
    WHEN r.metric_type = 'markup' THEN 'markup'
    WHEN r.metric_type IN ('cpu', 'memory', 'storage', 'gpu') THEN 'usage_cost'
    ELSE 'usage_cost'
END AS breakdown_category,

-- path (depth 4 for per-rate rows)
CASE
    WHEN r.cost_category_id IS NULL OR cc.name != 'Platform'
    THEN 'project.' ||
         CASE WHEN r.metric_type = 'markup' THEN 'markup'
              ELSE 'usage_cost' END ||
         '.' || r.custom_name
    ELSE 'overhead.' ||
         CASE WHEN r.metric_type = 'markup' THEN 'markup'
              ELSE 'usage_cost' END ||
         '.' || r.custom_name
END AS path,

-- depth: 4 for per-rate leaf rows (Source 1 in breakdown population SQL).
-- Distribution per-rate leaf rows use depth 5 — see data-model.md hierarchy table.
4 AS depth,

-- parent_path
CASE
    WHEN r.cost_category_id IS NULL OR cc.name != 'Platform'
    THEN 'project.' ||
         CASE WHEN r.metric_type = 'markup' THEN 'markup'
              ELSE 'usage_cost' END
    ELSE 'overhead.' ||
         CASE WHEN r.metric_type = 'markup' THEN 'markup'
              ELSE 'usage_cost' END
END AS parent_path
```

Intermediate tree nodes (depth 1-3: `total_cost`, `project`,
`project.usage_cost`) are aggregated from per-rate leaf rows (depth 4)
using a separate INSERT with `GROUP BY top_category, breakdown_category`
and `SUM(cost_value)`. Distribution per-rate leaf rows (depth 5, e.g.,
`overhead.platform_distributed.usage_cost.OpenShift_Subscriptions`) are
sourced from `RatesToUsage` distributed rows in breakdown population SQL —
see [`poc/reporting_ocp_cost_breakdown_p.sql`](./poc/reporting_ocp_cost_breakdown_p.sql)
Source 2. With **IQ-9 Option 1** (selected), per-rate distribution is
reflected in `RatesToUsage` (`distributed_cost` rows); breakdown
population reads those rows (see [IQ-9](#iq-9-distribution-per-rate-identity-gap)).
Option 2 (back-allocation in breakdown SQL only) remains documented as a
viable fallback — see [README § IQ-9 Options](#iq-9-distribution-per-rate-identity-gap).

### IQ-5: SQL approach for RatesToUsage INSERTs (Phase 2)

**Problem**: 12 rate-component INSERTs need a home.

**Proposal: Separate SQL file with CTE + single INSERT using UNION ALL.**

New file: `sql/openshift/cost_model/insert_usage_rates_to_usage.sql`,
called by a new accessor method after `populate_usage_costs()`.

```sql
WITH base AS (
    SELECT
        usage_start, cluster_id, node, namespace, data_source,
        persistentvolumeclaim, pod_labels, volume_labels, all_labels,
        md5(COALESCE(pod_labels::text, '')
            || COALESCE(volume_labels::text, '')
            || COALESCE(all_labels::text, '')) AS label_hash,  -- R13
        cost_category_id, source_uuid, report_period_id, cluster_alias,
        sum(pod_usage_cpu_core_hours) AS cpu_usage_hours,
        sum(pod_request_cpu_core_hours) AS cpu_request_hours,
        ...
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE ...
    GROUP BY usage_start, cluster_id, node, namespace, data_source,
             persistentvolumeclaim, pod_labels, volume_labels, all_labels,
             cost_category_id, source_uuid, report_period_id, cluster_alias
)
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (...)
SELECT ... label_hash, 'cpu_core_usage_per_hour', 'cpu', cpu_usage_hours * {{cpu_core_usage_per_hour}}, ...
FROM base WHERE {{cpu_core_usage_per_hour}} != 0
UNION ALL
SELECT ... label_hash, 'cpu_core_request_per_hour', 'cpu', cpu_request_hours * {{cpu_core_request_per_hour}}, ...
FROM base WHERE {{cpu_core_request_per_hour}} != 0
UNION ALL
...
```

This is a single SQL statement (CTE + INSERT with UNION ALL), so it
works with `_prepare_and_execute_raw_sql_query`. The `WHERE rate != 0`
clauses skip zero-rate components, avoiding unnecessary rows.
`UNION ALL` with a CTE exists as a pattern in koku
(`ocp_tag_mapping_update_daily_summary.sql`).

The CTE GROUP BY matches `usage_costs.sql` exactly (including
`pod_labels`, `volume_labels`, `persistentvolumeclaim`, `all_labels`).
The `label_hash` column (R13 mitigation) is computed in the CTE and
used by the aggregation step for GROUP BY / JOIN instead of JSONB
equality. See [sql-pipeline.md § The Aggregation Step](./sql-pipeline.md#the-aggregation-step).

### IQ-6: `PriceList.usage_start/usage_end` (Phase 1)

**Problem**: Speculative fields not in the PRD.

**Proposal: Remove them.**

Koku's existing models are minimal. `CostModel` has no date-bounding
on rates. Adding speculative fields contradicts the YAGNI principle.
If time-bounded pricing is needed later, the columns can be added in a
future migration with no impact on existing data.

### IQ-7: Backward compatibility for `custom_name` (Phase 1) — RESOLVED

**Problem**: Adding `custom_name` as required breaks existing API
consumers.

**Resolution**: Tech lead confirmed auto-generation approach.
`custom_name` is `required=False` with auto-generation from
`description` or `metric.name`.

Koku's `RateSerializer` already has `description` as `required=False`.
Apply the same pattern to `custom_name`:

```python
custom_name = serializers.CharField(max_length=50, required=False, allow_blank=True)
```

If not provided, auto-generate from `description` or `metric.name`
using the same `generate_custom_name()` logic from migration M3. This
is backward compatible — existing API consumers work without changes,
and new consumers can set meaningful names.

### IQ-8: `cost_type` on `OCPCostUIBreakDownP` (Phase 4)

**Problem**: `cost_type` is ambiguous for distribution rows.

**Resolution**: Tech lead and PM confirmed `cost_type` is not needed.
Column dropped from `OCPCostUIBreakDownP`. If categorization is needed
in the future, it will be a different breakdown with user-defined
categories.

### IQ-9: Distribution per-rate identity gap

**Problem**: Distribution SQL (`distribute_platform_cost.sql`,
`distribute_worker_cost.sql`, `distribute_unattributed_storage_cost.sql`,
`distribute_unattributed_network_cost.sql`, `distribute_unallocated_gpu_cost.sql`)
reads **aggregated** `cost_model_*_cost` columns from the daily summary
and produces a single `distributed_cost` per namespace/node. Per-rate
identity is completely lost.

For example: Platform cost = $60 ($20 from "OpenShift Subscriptions" CPU
rate + $30 from "RHEL" rate + $10 from memory rate). After distribution,
Project A gets `distributed_cost = $12` — with no record of which rates
contributed to that $12.

**Impact on breakdown tree**: The tree can only show distribution nodes
at depth 3 (e.g., `overhead.platform_distributed`) without per-rate
drill-down. The aspirational depth 5 structure
(`overhead.platform_distributed.usage_cost.OpenShift_Subscriptions`)
is unreachable without changes to the distribution data flow. See
[data-model.md § Tree Structure Definition](./data-model.md#tree-structure-definition).

#### Investigation findings

Source code analysis of the 5 distribution SQL files and their
orchestration (`ocp_cost_model_cost_updater.py`,
`ocp_report_db_accessor.py`) revealed the following constraints:

1. **Infrastructure costs are in the mix.** Distribution sums:
   ```
   total_cost = infrastructure_raw_cost + infrastructure_markup_cost
              + cost_model_cpu_cost + cost_model_memory_cost
              + cost_model_volume_cost
   ```
   Infrastructure raw/markup comes from cloud billing, not cost model
   rates. Historically it did not exist in `RatesToUsage`. Any per-rate
   breakdown must account for the infrastructure portion separately.
   **IQ-9 Option 1** adds a single "Raw Cost" row per namespace/day in
   `RatesToUsage` (`monthly_cost_type = 'raw_cost'`) so that portion
   participates in the same per-rate distribution path.

2. **Option 1 is feasible with a rewritten pipeline.**
   - Distribution reads **usage metrics** (`pod_effective_usage_*_hours`)
     from the daily summary and **per-rate costs** from `RatesToUsage`.
   - Distribution uses **DELETE + INSERT** (same pattern as elsewhere in
     the pipeline), not `UPDATE` on existing rows.
   - **Old distribution SQL files are deprecated; new files are created**
     for rollback parity (swap file set to revert behavior).
   - **Infrastructure raw cost** is represented as a single "Raw Cost"
     row per namespace/day in `RatesToUsage`, tagged with
     `monthly_cost_type = 'raw_cost'`, so it participates in the same
     per-rate distribution math as cost-model rows.
   - A **`distributed_cost` column on `RatesToUsage`** stores recipient
     rows (+cost) and source negation rows (−cost) written by
     distribution.

3. **All 5 distribution types follow the same formula:**
   ```
   distributed_cost = (pod_effective_usage / total_usage) * total_cost
   ```
   The allocation is proportional to CPU or memory usage (controlled
   by the `{{distribution}}` parameter). Source namespaces (Platform,
   Worker unallocated, etc.) receive a negation row (`0 - total_cost`)
   to zero out their cost.

4. **New orchestration flow (Option 1).**
   - `RatesToUsage INSERT` (per-rate usage and monthly/tag rows) →
     **raw cost INSERT** (one "Raw Cost" row per namespace/day,
     `monthly_cost_type = 'raw_cost'`) → **distribution** (reads
     per-rate costs from `RatesToUsage` and `pod_effective_usage_*_hours`
     from the daily summary; **DELETE + INSERT** of distributed rows with
     `distributed_cost` on `RatesToUsage`) → **aggregation** (sums all
     `RatesToUsage` rows, including distributed rows, into daily summary
     `cost_model_*_cost` / related columns) → UI summary.
   - Distribution writes **per-rate distributed rows** (recipient +cost,
     source −cost) back into `RatesToUsage`; the aggregation step is what
     lands consolidated totals on the daily summary.

#### Options evaluated

| # | Approach | Invasiveness | Per-rate identity | Infrastructure handling | Risk |
|---|----------|-------------|-------------------|------------------------|------|
| 1 | **Rewrite distribution SQL** to read from `RatesToUsage` + daily summary usage (**selected**) | HIGH (new distribution files; deprecate old; GPU sequencing unchanged in importance) | Full | Raw cost as dedicated `RatesToUsage` row (`monthly_cost_type = 'raw_cost'`) | Regression risk mitigated by new files + rollback via old file set |
| 2 | Back-allocate proportionally (breakdown population only) | MEDIUM (no distribution rewrite) | Cost model rates: full. Infrastructure: one aggregate entry. | "Infrastructure" entry under each distribution node | Proportional approximation; join complexity — **viable fallback** |
| 3 | Show aggregate only | NONE | None | N/A | Feature value reduced for overhead drill-down |

#### Recommendation: Option 1 — distribute at per-rate level

**Rationale**:

- **Tech lead selected Option 1.** Per-rate identity is preserved in
  `RatesToUsage` end-to-end; no proportional back-allocation step is
  required for the primary path.
- **Single source of truth** extends to distributed costs: recipient
  and negation rows live in `RatesToUsage` with `distributed_cost`,
  and aggregation rolls them into the daily summary like other per-rate
  rows.
- **Infrastructure raw cost** is first-class via one synthetic row per
  namespace/day, so it participates in the same allocation formula as
  rate-derived costs.
- **DELETE + INSERT** and **deprecated old files / new files** match
  existing operational and rollback patterns.
- **GPU sequencing** has always been critical in distribution; Option 1
  does not introduce a new class of GPU risk beyond existing ordering
  constraints.

#### How Option 1 works

1. **Orchestration**: `RatesToUsage INSERT` → raw cost row INSERT →
   distribution (reads `RatesToUsage` costs + daily summary usage
   metrics) → aggregation → daily summary → UI summary.
2. **Inputs**: Distribution reads **per-rate costs** from `RatesToUsage`
   and **`pod_effective_usage_*_hours`** (and related usage fields as
   today) from `reporting_ocpusagelineitem_daily_summary`.
3. **Writes**: Distribution **DELETE + INSERT** — recipient namespaces
   get per-rate rows with **positive** `distributed_cost`; source
   namespaces get **negation** rows so totals reconcile.
4. **Aggregation**: Sums all `RatesToUsage` rows (including distributed
   rows) into daily summary cost columns.
5. **Infrastructure**: **Raw Cost** appears as a single row in
   `RatesToUsage` per namespace/day (`monthly_cost_type = 'raw_cost'`),
   included in the same distribution and aggregation path.

Option 2 (back-allocation) remains a documented fallback if the team
needs to avoid touching distribution SQL — see
[sql-pipeline.md § Back-Allocation SQL](./sql-pipeline.md#back-allocation-sql-sketch).

#### Resolved

Tech lead and PM confirmed: **Option 1** (per-rate distribution in
`RatesToUsage`), **`distributed_cost` on `RatesToUsage`**, **raw cost
row** semantics, **DELETE + INSERT**, **new files with deprecated old
files for rollback**, **usage metrics from daily summary**, and
**`cost_type` removed from `OCPCostUIBreakDownP`** (IQ-8). No further
open questions on this decision set.

---

## Quick Start

| Your goal | Start here |
|-----------|------------|
| Understand the new database tables and migration | [data-model.md](./data-model.md) |
| Understand SQL pipeline changes and per-rate write strategy | [sql-pipeline.md](./sql-pipeline.md) |
| Understand API and frontend integration points | [api-and-frontend.md](./api-and-frontend.md) |
| Understand the phased delivery plan and risks | [phased-delivery.md](./phased-delivery.md) |

---

## Reading Order

### For the reviewing engineer

1. This README (open questions first)
2. [data-model.md](./data-model.md) — new tables, schema, migration
3. [sql-pipeline.md](./sql-pipeline.md) — how per-rate data flows through the SQL pipeline
4. [phased-delivery.md](./phased-delivery.md) — what ships when, rollback strategy

### For frontend engineers

1. [api-and-frontend.md](./api-and-frontend.md) — new endpoint, response format, component plan

---

## Document Catalog

| Document | Type | Summary |
|----------|------|---------|
| [data-model.md](./data-model.md) | DD | New Django models (`PriceList`, `Rate`, `RatesToUsage` / `rates_to_usage`, `OCPCostUIBreakDownP`), `custom_name` migration strategy, tree structure definition |
| [sql-pipeline.md](./sql-pipeline.md) | DD | Current vs proposed data flow, SQL file inventory (20+ files across 3 paths), `CostModelDBAccessor` changes, aggregation step design |
| [api-and-frontend.md](./api-and-frontend.md) | DD | Cost model API changes (`custom_name`, dual-write), new breakdown endpoint, frontend components, export integration |
| [phased-delivery.md](./phased-delivery.md) | DD | 5-phase plan with per-phase artifacts, validation criteria, rollback strategy, risk register |
| [risk-register.md](./risk-register.md) | Ref | Consolidated risk register (R1-R19), decision rationales, benchmarking plan, phase matrix |

---

## Architecture at a Glance

### Current Data Flow

```mermaid
graph TD
    CM["CostModel.rates<br/>(JSON blob)"] --> Accessor["CostModelDBAccessor<br/>price_list property"]
    Accessor --> UsageSQL["usage_costs.sql<br/>+ monthly_cost_*.sql<br/>+ *_tag_rates.sql"]
    UsageSQL -->|"cost_model_cpu_cost<br/>cost_model_memory_cost<br/>cost_model_volume_cost<br/>(aggregated scalars)"| DailySummary["reporting_ocpusagelineitem<br/>_daily_summary"]
    DailySummary --> DistSQL["distribute_platform_cost.sql<br/>distribute_worker_cost.sql<br/>+ 3 more"]
    DistSQL -->|"distributed_cost"| DailySummary
    DailySummary --> UISummary["reporting_ocp_cost_summary_*_p<br/>(12 UI summary tables)"]
    UISummary --> API["Report API<br/>/reports/openshift/costs/"]
    API --> Sankey["Sankey Chart<br/>(costBreakdownChart.tsx)"]
```

### Proposed Data Flow (IQ-1 resolved: single source of truth)

```mermaid
graph TD
    CM["CostModel.rates (JSON)<br/>+ Rate table (new)"] --> Accessor["CostModelDBAccessor<br/>reads from Rate table"]

    Accessor --> RTU_SQL["insert_usage_rates_to_usage.sql<br/>+ monthly_cost_*.sql<br/>+ *_tag_rates.sql<br/>+ raw cost row per ns/day"]
    RTU_SQL -->|"per-rate rows at fine grain<br/>(pod_labels, volume_labels,<br/>persistentvolumeclaim, all_labels)"| RatesToUsage["RatesToUsage<br/>(new, partitioned)<br/>table: rates_to_usage"]

    DailySummary["reporting_ocpusagelineitem<br/>_daily_summary"] -->|"pod_effective_usage_*_hours<br/>(usage metrics)"| DistSQL["distribute_*.sql<br/>(rewritten, new files)"]
    RatesToUsage -->|"per-rate calculated costs"| DistSQL
    DistSQL -->|"DELETE + INSERT<br/>distributed_cost (+/− per rate)"| RatesToUsage

    RatesToUsage -->|"SUM by metric_type<br/>(DELETE + INSERT)"| AggSQL["aggregate_rates_to<br/>_daily_summary.sql"]
    AggSQL -->|"cost_model_*_cost<br/>+ consolidated totals"| DailySummary

    DailySummary --> UISummary["reporting_ocp_cost_summary_*_p<br/>(unchanged)"]

    RatesToUsage --> BreakdownSQL["reporting_ocp_cost<br/>_breakdown_p.sql (new)"]
    %% Breakdown reads from RatesToUsage only (includes distributed rows)
    BreakdownSQL --> BreakdownTable["OCPCostUIBreakDownP<br/>(new, partitioned)"]
    BreakdownTable --> BreakdownAPI["Breakdown API (new)<br/>/breakdown/openshift/cost/"]
    BreakdownAPI --> FlatTree["Flat/Tree View<br/>(new frontend component)"]

    UISummary --> API["Report API<br/>(unchanged)"]
    API --> Sankey["Sankey Chart<br/>(unchanged)"]
```

The key architectural change: **`RatesToUsage` is the single source of
truth** for cost model calculations. With **IQ-9 Option 1**, cost data
flows: `RatesToUsage` INSERT (including raw cost rows) → **distribution**
(reads `RatesToUsage` + daily summary usage metrics; writes per-rate
`distributed_cost` rows back to `RatesToUsage` via DELETE + INSERT) →
**aggregation** → daily summary → UI summary. The report API and Sankey
continue to consume the same daily summary and UI summary surfaces;
distribution is no longer a daily-summary-only scalar step — it is
per-rate on `RatesToUsage` before the aggregation roll-up.

There is no temporary dual-path. `usage_costs.sql` direct-write is
replaced by `RatesToUsage` INSERT + aggregation in Phase 2. A CI-only
validation query verifies aggregation correctness in integration tests.

---

## Key Design Decisions

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| Aggregation step | Kept (single source of truth) | Tech lead confirmed: eliminates dual-path maintenance and data integrity risk |
| Breakdown API format | Flat DB rows, both flat and nested API responses | Tech lead confirmed: UI mocks require both views; flat DB storage with server-side tree construction for nested view |
| `custom_name` backward compatibility | `required=False` with auto-generation | Tech lead confirmed: existing API consumers work unchanged; new consumers can set meaningful names |
| Feature flags | None | Dual-write (JSON + Rate table) is the rollback mechanism; no Unleash flags |
| Distribution SQL changes | **RESOLVED** — IQ-9 Option 1 (distribute at per-rate level) | Distribution rewritten: reads per-rate costs from `RatesToUsage` and usage metrics from daily summary; **DELETE + INSERT** of `distributed_cost` rows back to `RatesToUsage`; aggregation then rolls up to daily summary. Old SQL files deprecated, new files for rollback. Option 2 (back-allocate) remains a documented fallback. |
| Sankey chart changes | None | Sankey reads from existing report API which is unchanged |
| Rate table read path | Switched in Phase 1, permanent in Phase 5 | Dual-write preserves JSON for rollback |
| Future scalability | Single source of truth scales for upcoming features | Price List Lifecycles (multiple price lists) and Consumer & Provider (multiple cost models) compound dual-write overhead; single calculation point avoids this |

---

## Changelog

All documents in this directory (`docs/architecture/cost-breakdown/`)
are versioned together. Each version corresponds to a commit on the
`COST-7249/cost-breakdown-design` branch.

| Version | Date | Commit | Summary |
|---------|------|--------|---------|
| v1.0 | 2026-03-17 | `9cb337ab9` | Initial technical design: 5 documents (README, data-model, sql-pipeline, api-and-frontend, phased-delivery) + 4 PoC artifacts. Covers schema normalization, SQL pipeline changes, API/frontend plan, and 5-phase delivery. 8 implementation questions (IQ-1 through IQ-8), 4 open questions (OQ-1 through OQ-4), 12 risks (R1-R12). |
| v1.1 | 2026-03-17 | `c1b28bc82` | Address gemini-code-assist review: fix off-by-one in `generate_custom_name` (`[:47]` → `[:46]`), replace `Rate.objects.create()` loop with `bulk_create()`. |
| v2.0 | 2026-03-17 | `1e05f2343` | **IQ-1 RESOLVED** (single source of truth). Major redesign: add 4 fine-grained columns to `RatesToUsage` (`pod_labels`, `volume_labels`, `persistentvolumeclaim`, `all_labels`). Aggregation SQL redesigned as DELETE + INSERT (replaces `usage_costs.sql` direct-write from Phase 2). Remove all dual-path language. Add R13 (JSONB JOIN performance). Update all 5 documents and PoC SQL. |
| v2.1 | 2026-03-17 | `369dbda50` | **IQ-3 RESOLVED** (flat DB rows, both flat and nested API responses). **IQ-7 RESOLVED** (auto-generate `custom_name`). Fix tree depth inconsistency (align hierarchy table with PoC SQL). Add future scalability section (Price List Lifecycles, Consumer & Provider). Document IQ-9 (distribution per-rate identity gap) as new open question. |
| v2.2 | 2026-03-17 | — | **IQ-9 investigation complete.** Expand IQ-9 with full source code analysis of distribution SQL. Recommend Option 2 (back-allocate proportionally). Add SQL sketch for back-allocation to sql-pipeline.md. Update data-model.md tree to show depth 5 structure. Add R14 (rounding), R15 (JOIN complexity). Add this changelog. |
| v2.3 | 2026-03-17 | — | **Blast-radius triage.** Fix 8 cross-document inconsistencies: remove erroneous `resource_id` from aggregation SQL sketch (G4, HIGH), fix RateSerializer `required=True` → `required=False` (G5), align M1 DDL with IQ-6 proposal (G3), add "infrastructure" breakdown_category (G2), update IQ-9 PoC artifact column (G1), add IQ-9 dependency to IQ-4 Source 2 (G8), fix serializer reference in phased-delivery (G6), document `labels` field purpose (G7). Add R16 (aggregation GROUP BY granularity), R17 (markup ORM overhead). |
| v2.4 | 2026-03-17 | — | **Risk mitigation.** R13 MITIGATED: add `label_hash` column to `RatesToUsage` model, DDL, PoC SQL, aggregation SQL, and validation SQL. R14: add reconciliation check SQL. R17: add SQL-based markup INSERT fallback. R6: add 8-point SQL testing checklist. R2/R3: add Phase 2 benchmarking plan with acceptance criteria. Update risk register: downgrade R13 from HIGH to MITIGATED. |
| v2.5 | 2026-03-17 | — | **Decision rationales.** Add alternatives-evaluated tables with pros/cons/verdict for all actively mitigated risks: R2/R3 (DELETE+INSERT aggregation, 3 options), R6 (per-file-per-PR, 4 options), R11 (single DELETE scope, 3 options), R13 (label_hash, 5 options — already in v2.4), R14 (reconciliation check, 3 options), R15 (3-CTE back-allocation, 4 options), R17 (ORM-first + SQL fallback, 3 options). |
| v3.0 | 2026-03-19 | — | **IQ-9 RESOLVED (Option 1)**, **IQ-6 RESOLVED**, **IQ-8 RESOLVED**. Adopt per-rate distribution (Option 1): distribution reads from `RatesToUsage` + daily summary usage, writes per-rate distributed rows back to `RatesToUsage`. Drop `cost_type` from `OCPCostUIBreakDownP`. Rename `CostModelRatesToUsage` → `RatesToUsage` / `cost_model_rates_to_usage` → `rates_to_usage`. Add `distributed_cost` column and infrastructure raw cost row. Update mermaid: distribution before aggregation. R14 eliminated, R15 replaced, R18 added. |
| v3.1 | 2026-03-19 | — | **Risk extraction.** Create [risk-register.md](./risk-register.md) as consolidated risk reference (R1-R19). Slim down decision rationale tables in data-model.md, sql-pipeline.md, phased-delivery.md to one-line links. Add R19 (aggregation + `distributed_cost` — open). Update document catalog. |
