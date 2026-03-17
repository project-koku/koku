# Phased Delivery Plan

This document maps each phase to specific code artifacts, defines
validation criteria, rollback strategies, and the risk register.

---

## Decisions Pending Tech Lead Review

Three design decisions need confirmation. See
[README.md § Decisions Needed from Tech Lead](./README.md#decisions-needed-from-tech-lead)
for full context and PoC references.

| Decision | Impact on this plan |
|----------|-------------------|
| **IQ-1**: Drop aggregation step | If confirmed: Phase 2 removes `aggregate_rates_to_daily_summary.sql` and `validate_rates_against_daily_summary.sql` from production artifacts (validation becomes test-only). Phase 3 "aggregation promotion" step is removed. Phase 5 scope is reduced. |
| **IQ-3**: Flat-row API response | If confirmed: Phase 4 uses standard `OCPReportQueryHandler` with `provider_map.py` entry instead of custom nested serializer. |
| **IQ-7**: `custom_name` optional | If confirmed: Phase 1 `RateSerializer` uses `required=False` with auto-generation. No API version bump needed. |

---

## Phase Overview

```mermaid
graph LR
    P1["Phase 1<br/>Schema<br/>Normalization"] --> P2["Phase 2<br/>Rate Calculation<br/>Isolation"]
    P2 --> P3["Phase 3<br/>Complete SQL<br/>Migration"]
    P3 --> P4["Phase 4<br/>Breakdown<br/>UI + API"]
    P4 --> P5["Phase 5<br/>Cleanup"]
```

| Phase | Goal | User-Facing? | Migrations | Rollback Strategy |
|-------|------|-------------|------------|-------------------|
| 1 | Normalize rate storage | No | M1, M2, M3 | Revert code to JSON read path; dual-write preserves JSON |
| 2 | Per-rate cost tracking (usage costs only) | No | M4 | Revert code; truncate `RatesToUsage`; direct-write still active |
| 3 | Migrate all remaining SQL files | No | None | Revert individual SQL files |
| 4 | Expose breakdown data to UI | Yes | M5 | Unregister URL; leave table empty |
| 5 | Remove legacy JSON path | No | M6 | Restore from backup |

---

## Phase 1: Schema Normalization

**Goal**: Normalize rate storage without changing cost calculation behavior.

### Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| `PriceList` model | `cost_models/models.py` | New Django model |
| `Rate` model | `cost_models/models.py` | New Django model with `custom_name` |
| Migration M1 | `cost_models/migrations/XXXX_create_price_list.py` | DDL for `cost_model_price_list` |
| Migration M2 | `cost_models/migrations/XXXX_create_rate.py` | DDL for `cost_model_rate` |
| Migration M3 | `cost_models/migrations/XXXX_migrate_json_to_rate.py` | Data migration: JSON → Rate rows |
| `RateSerializer` update | `cost_models/serializers.py` | Add `custom_name` field (required) |
| `CostModelSerializer` update | `cost_models/serializers.py` | Dual-write to JSON + Rate table |
| `CostModelDBAccessor` update | `masu/database/cost_model_db_accessor.py` | Read from Rate table (dual-write preserves JSON as fallback) |

### Validation

- All existing `CostModel` rows have corresponding `PriceList` + `Rate`
  rows after M3
- `custom_name` is populated for every rate (no NULLs)
- API backward-compatible: `GET /cost-models/{uuid}/` returns rates with
  `custom_name` added (existing fields unchanged)
- `CostModelDBAccessor.price_list` returns identical dict from Rate table
  as from JSON (compare with unit test)
- Cost calculation results unchanged (run existing test suite)

### Rollback

1. Revert `CostModelDBAccessor` code → reads from JSON (which is still
   populated via dual-write)
2. Revert dual-write code → API writes to JSON only
3. Reverse M3 → remove `custom_name` from JSON, delete Rate/PriceList rows
4. Drop tables via reverse M2, M1

---

## Phase 2: Rate Calculation Isolation

**Goal**: Write per-rate cost data to `CostModelRatesToUsage` for usage
costs (`usage_costs.sql` only).

> **Previously blocked by** OQ-1 and OQ-3 — both resolved. See
> [README.md](./README.md).

### Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| `CostModelRatesToUsage` model | `reporting/provider/ocp/models.py` | New partitioned Django model |
| Migration M4 | `reporting/migrations/XXXX_create_rates_to_usage.py` | DDL for `cost_model_rates_to_usage` |
| `usage_costs.sql` | `masu/database/sql/openshift/cost_model/usage_costs.sql` | **Unchanged** (direct-write to daily summary preserved per IQ-1 proposal) |
| New RatesToUsage INSERT SQL | `masu/database/sql/openshift/cost_model/insert_usage_rates_to_usage.sql` | CTE + UNION ALL producing per-rate rows — see [PoC](./poc/insert_usage_rates_to_usage.sql) |
| Orchestration update | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | Call RatesToUsage INSERT after `usage_costs.sql`; no aggregation step (IQ-1) |
| Accessor update | `masu/database/ocp_report_db_accessor.py` | New `populate_usage_rates_to_usage()` method; `populate_usage_costs()` unchanged |
| Markup → RatesToUsage | `masu/database/ocp_report_db_accessor.py` | New `populate_markup_rates_to_usage()` method (ORM INSERT into `RatesToUsage` after markup UPDATE) |
| Validation SQL (test-only) | `masu/database/sql/openshift/cost_model/validate_rates_against_daily_summary.sql` | Read-only comparison query for CI regression tests (not runtime, per IQ-1) |
| Partition wiring | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | Call `get_or_create_partition()` before writing to `RatesToUsage` (not in `UI_SUMMARY_TABLES`) |
| Purge update | `masu/processor/ocp/ocp_report_db_cleaner.py` | Add `cost_model_rates_to_usage` to `purge_expired_report_data_by_date()` |
| DELETE for recalculation | `masu/database/ocp_report_db_accessor.py` | New `delete_rates_to_usage()` method — runs before each recalculation cycle |

### Validation

- `RatesToUsage` populated with per-rate rows for usage costs
- **CI validation test**: `validate_rates_against_daily_summary.sql`
  confirms `SUM(RatesToUsage.calculated_cost)` by metric_type matches
  the daily summary `cost_model_*_cost` columns at the (namespace, node,
  day) level. This runs in CI, not at runtime (per IQ-1 proposal).
- Existing test suite passes (cost calculation results unchanged —
  daily summary direct-write is untouched)
- Performance benchmark: query time on `RatesToUsage` for a tenant with
  30 rates, 100 namespaces, 30 days of data. Use
  [`poc/estimate_rates_to_usage_rows.sql`](./poc/estimate_rates_to_usage_rows.sql)
  to estimate row counts before implementation.

### Rollback

1. Revert new SQL file (`insert_usage_rates_to_usage.sql`) and
   orchestration code → RatesToUsage is no longer populated
2. Daily summary direct-write in `usage_costs.sql` is **unchanged** and
   continues to work — no revert needed for existing cost calculations
3. Truncate `cost_model_rates_to_usage` partitions if needed

---

## Phase 3: Complete SQL Migration

**Goal**: Extend per-rate tracking to all remaining cost SQL files.

### Artifacts

| Artifact | File(s) | Count |
|----------|---------|-------|
| Tag rate SQL updates (`sql/`) | `infrastructure_tag_rates.sql`, `supplementary_tag_rates.sql`, `default_*_tag_rates.sql` | 4 files |
| Monthly cost SQL updates (`sql/`) | `monthly_cost_cluster_and_node.sql`, `monthly_cost_persistentvolumeclaim.sql`, `monthly_cost_persistentvolumeclaim_by_tag.sql`, `monthly_cost_virtual_machine.sql` | 4 files |
| Node tag SQL update (`sql/`) | `node_cost_by_tag.sql` | 1 file |
| Trino SQL updates (`trino_sql/`) | `hourly_cost_virtual_machine.sql`, `hourly_cost_vm_tag_based.sql`, `hourly_vm_core.sql`, `hourly_vm_core_tag_based.sql`, `monthly_vm_core.sql`, `monthly_vm_core_tag_based.sql`, `monthly_project_tag_based.sql`, `monthly_cost_gpu.sql` | 8 files |
| Self-hosted SQL updates (`self_hosted_sql/`) | Same 8 files as Trino (standard PostgreSQL syntax) | 8 files |
| Accessor updates | `ocp_report_db_accessor.py` | `populate_monthly_cost_sql()`, `populate_tag_cost_sql()`, `populate_tag_usage_costs()`, `populate_tag_usage_default_costs()`, `populate_vm_usage_costs()`, `populate_tag_based_costs()` — all pass `custom_name` and write to RatesToUsage |

**Total**: 25 SQL file modifications + 6 accessor method updates.
No aggregation promotion — per IQ-1 proposal, the aggregation step is
removed. Each SQL file gains a RatesToUsage INSERT alongside its existing
daily summary INSERT.

**Trino dialect note**: The 8 `trino_sql/` files must use catalog-qualified
table names for the `RatesToUsage` INSERT (e.g.,
`INSERT INTO postgres.{{schema | sqlsafe}}.cost_model_rates_to_usage`). The 8
`self_hosted_sql/` files use standard PostgreSQL syntax since they execute
against PostgreSQL via Django. See
[sql-pipeline.md § Trino/Self-Hosted Architecture](./sql-pipeline.md#trinoself-hosted-architecture).

### Validation

- All cost types flow through `RatesToUsage` (usage, monthly, tag-based)
- Distributed costs calculated correctly (distribution SQL is unchanged
  but verify end-to-end)
- Full regression: compare total costs per tenant before/after
- Tag-based costs: verify `custom_name` attached correctly (one name per
  rate, not per tag value)

### Rollback

- Per-SQL-file: revert individual SQL files to remove `RatesToUsage` INSERT
- Full revert: revert all SQL files + accessor changes; `RatesToUsage`
  can be truncated

---

## Phase 4: Breakdown UI Table + API + Frontend

**Goal**: Expose per-rate breakdown data to users.

### Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| `OCPCostUIBreakDownP` model | `reporting/provider/ocp/models.py` | New partitioned Django model |
| Migration M5 | `reporting/migrations/XXXX_create_breakdown_p.py` | DDL for `reporting_ocp_cost_breakdown_p` |
| Breakdown population SQL | `masu/database/sql/openshift/ui_summary/reporting_ocp_cost_breakdown_p.sql` | Populate from `RatesToUsage` with tree paths |
| `UI_SUMMARY_TABLES` update | `reporting/provider/ocp/models.py` | Add to tuple for partition cleanup |
| Provider map entry | `api/report/ocp/provider_map.py` | `cost_breakdown` report type |
| View class | `api/report/ocp/view.py` | `OCPCostBreakdownView` |
| Serializer | `api/report/ocp/serializers.py` | `CostBreakdownSerializer` |
| URL registration | `api/urls.py` | `breakdown/openshift/cost/` |
| Frontend: report type | `api/reports/report.ts` | `ReportType.costBreakdown` |
| Frontend: API path | `api/reports/ocpReports.ts` | `breakdown/openshift/cost/` |
| Frontend: flat list | `routes/details/components/costOverview/` | `CostBreakdownTable` component |
| Frontend: tab restructure | `routes/details/components/breakdown/breakdownBase.tsx` | Move usage cards to "Usage overview" tab |
| Frontend: export | `api/export/ocpExport.ts` | Breakdown CSV export |

### Validation

- Breakdown table populated correctly (spot-check against `RatesToUsage`)
- API returns expected flat/tree structure (compare with PRD examples)
- Frontend renders breakdown table in Cost Overview tab
- Usage cards appear in new Usage Overview tab
- CSV export produces correct columns
- Existing Sankey chart still works (different data source)

### Rollback

- Don't register the URL → endpoint returns 404
- `OCPCostUIBreakDownP` can remain unpopulated (empty table)
- Revert frontend changes (tab restructure, new component)

---

## Phase 5: Cleanup

**Goal**: Remove legacy JSON rate storage path.

### Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| Migration M6 | `cost_models/migrations/XXXX_drop_rates_json.py` | `ALTER TABLE cost_model DROP COLUMN rates` |
| Remove dual-write | `cost_models/serializers.py` | API writes to Rate table only |
| Remove JSON read path | `masu/database/cost_model_db_accessor.py` | Remove `_price_list_from_json()` fallback |

### Preconditions

All of these must be verified before executing Phase 5:

- [ ] All tenants have been processed through the Rate table path
- [ ] No code path reads from `CostModel.rates` JSON
- [ ] Backup of `cost_model` table taken
- [ ] Full regression test suite passes

### Validation

- Full regression testing against all report endpoints
- Production monitoring for anomalies (cost values, API errors)
- Verify no references to `CostModel.rates` in codebase

### Rollback

- Restore `rates` column from backup
- Re-add dual-write code
- This is the only phase where rollback is practically difficult

---

## Risk Register

| ID | Risk | Severity | Likelihood | Phase | Mitigation |
|----|------|----------|------------|-------|------------|
| R1 | `usage_costs.sql` has 6 entangled CPU cost components that are hard to decompose into named rates | ~~HIGH~~ **MITIGATED** | ~~HIGH~~ LOW | 2 | **RESOLVED (OQ-1)**: All 6 map 1:1 to distinct rate metrics in `COST_MODEL_USAGE_RATES`. CTE approach avoids GROUP BY duplication. 12x row multiplier quantified. |
| R2 | Aggregation step produces different values than direct-write (rounding, NULLs, missing rows) | HIGH | MEDIUM | 2 | **RESOLVED (OQ-3)**: No existing dual-path infrastructure in koku. Strategy: regression tests + Phase 2 read-only validation query (`validate_rates_against_daily_summary.sql`). |
| R3 | Row explosion in `RatesToUsage` causes query timeouts | MEDIUM | MEDIUM | 2 | 12x multiplier quantified (OQ-1). Benchmark with realistic data (12 rates x 100 namespaces x 30 days = 36M rows/month worst case); partition by month |
| R4 | Monthly cost rates produce more rows than expected (per-namespace allocation) | ~~MEDIUM~~ **MITIGATED** | ~~HIGH~~ LOW | 3 | **RESOLVED (OQ-2)**: GROUP BY is `(usage_start, source_uuid, cluster_id, node, namespace, pod_labels, cost_category_id)`. Row count per monthly rate quantifiable from existing data. |
| R5 | Cost category reclassification invalidates breakdown tree | ~~MEDIUM~~ **MITIGATED** | ~~LOW~~ NONE | 4 | **RESOLVED (OQ-4)**: `CostGroupsAddView`/`CostGroupsRemoveView` already trigger `update_summary_tables` which chains into full cost model recomputation. No special handling needed. |
| R6 | 25 SQL file modifications across 3 paths introduce regressions | MEDIUM | MEDIUM | 3 | Modify one file at a time; regression tests per file; revert individual files if needed |
| R7 | Dual-write divergence (JSON and Rate table drift) | LOW | LOW | 1-4 | `_sync_rate_table` does delete-all + recreate on every write; no partial sync |
| R8 | `custom_name` migration produces ugly names for rates with empty descriptions | LOW | HIGH | 1 | Acceptable per PRD ("ugly but functional"); users can rename after migration |
| R9 | Frontend tab restructure breaks existing user workflows | LOW | LOW | 4 | Usage cards move to adjacent tab, not removed; link/breadcrumb from old location |
| R10 | Trino SQL dialect requires catalog-qualified table names for `RatesToUsage` INSERT | MEDIUM | MEDIUM | 3 | Test `trino_sql/` files with Trino locally; `self_hosted_sql/` files use standard PostgreSQL syntax and are lower risk |
| R11 | Concurrent cost model updates with overlapping date ranges create duplicate `RatesToUsage` rows | MEDIUM | LOW | 2-3 | Existing Redis lock (`WorkerCache.lock_single_task`) prevents identical `(schema, provider, start, end)` runs; DELETE-before-INSERT pattern (Step 0) clears stale rows per recalculation window; risk is limited to rare overlapping-range scenarios |
| R12 | `CostModelManager.update()` has no `@transaction.atomic` — dual-write (JSON save + Rate table sync) can partially fail | MEDIUM | MEDIUM | 1 | Add `@transaction.atomic` to `update()`. `create()` already has it. See [api-and-frontend.md](./api-and-frontend.md). |

### Risk × Phase Matrix

```
          Phase 1    Phase 2    Phase 3    Phase 4    Phase 5
R1          ✓          ✓ (mitigated — OQ-1 resolved)
R2                     ██
R3                     ██
R4          ✓          ✓          ✓ (mitigated — OQ-2 resolved)
R5          ✓          ✓          ✓          ✓ (mitigated — OQ-4 resolved)
R6                                ██
R7          ██         ██         ██         ██
R8          ██
R9                                           ██
R10                               ██
R11                    ██         ██
R12         ██
```

---

## Timeline Considerations

Phase 1 can start immediately — it has no open questions. The
`_price_list_from_rate_table()` format compatibility has been validated
by PoC tests ([`poc/price_list_compat.py`](./poc/price_list_compat.py),
6/6 pass).

Phase 2 is **unblocked** — all four open questions (OQ-1 through OQ-4)
have been resolved via source code triage. The RatesToUsage INSERT SQL
has been prototyped ([`poc/insert_usage_rates_to_usage.sql`](./poc/insert_usage_rates_to_usage.sql)).
Implementation can proceed immediately after Phase 1 ships, pending
IQ-1 confirmation from tech lead.

Phases 3 and 4 can overlap: Phase 3 SQL changes are independent of
Phase 4 API/frontend work, as long as Phase 2 is complete. The
breakdown table population SQL has been prototyped
([`poc/reporting_ocp_cost_breakdown_p.sql`](./poc/reporting_ocp_cost_breakdown_p.sql)).

Phase 5 should only run after Phase 4 has been validated in production
for a sufficient period (recommended: at least one full billing cycle).

### Blocking dependencies

```
Phase 1 ← no blockers (start now)
Phase 2 ← Phase 1 + IQ-1 confirmation
Phase 3 ← Phase 2
Phase 4 ← Phase 3 + IQ-3 confirmation (flat rows vs nested)
Phase 5 ← Phase 4 validated in production
```
