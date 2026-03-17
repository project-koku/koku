# Phased Delivery Plan

This document maps each phase to specific code artifacts, defines
validation criteria, rollback strategies, and the risk register.

---

## Decisions Pending Tech Lead Review

Three design decisions have been resolved (IQ-1, IQ-3, IQ-7). See
[README.md § Decisions Needed from Tech Lead](./README.md#decisions-needed-from-tech-lead)
for full context and PoC references.

| Decision | Status | Impact on this plan |
|----------|--------|-------------------|
| **IQ-1**: Single source of truth via RatesToUsage with aggregation | **RESOLVED** | Phase 2 replaces `usage_costs.sql` direct-write with RatesToUsage INSERT + aggregation (DELETE + INSERT). No dual-path. Fine-grained columns added to `CostModelRatesToUsage`. CI validation query verifies correctness. |
| **IQ-3**: Flat-row DB storage with both flat and nested API responses | **RESOLVED** | Phase 4 uses standard `OCPReportQueryHandler` with `provider_map.py` entry for flat view; tree view reconstructed from flat rows server-side via `?view=tree`. |
| **IQ-7**: `custom_name` optional with auto-generation | **RESOLVED** | Phase 1 `RateSerializer` uses `required=False` with auto-generation from `description` or `metric.name`. No API version bump needed. |
| **IQ-9**: Distribution per-rate identity | Open | Affects Phase 4 breakdown tree depth for distributed costs. Distribution SQL currently loses per-rate identity. See [README.md § IQ-9](./README.md#iq-9-distribution-per-rate-identity-gap). |

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
| RatesToUsage INSERT SQL | `masu/database/sql/openshift/cost_model/insert_usage_rates_to_usage.sql` | CTE + UNION ALL producing per-rate rows at fine granularity — **replaces** `usage_costs.sql` direct-write. See [PoC](./poc/insert_usage_rates_to_usage.sql) |
| Aggregation SQL | `masu/database/sql/openshift/cost_model/aggregate_rates_to_daily_summary.sql` | DELETE + INSERT: aggregates `RatesToUsage` → daily summary `cost_model_*_cost` columns. Replaces `usage_costs.sql` direct-write. |
| Orchestration update | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | Replace `self._update_usage_costs()` with RatesToUsage INSERT + aggregation. No dual-path. |
| Accessor update | `masu/database/ocp_report_db_accessor.py` | New `populate_usage_rates_to_usage()` and `aggregate_rates_to_daily_summary()` methods; `populate_usage_costs()` retired |
| Markup → RatesToUsage | `masu/database/ocp_report_db_accessor.py` | New `populate_markup_rates_to_usage()` method (ORM INSERT into `RatesToUsage` after markup UPDATE) |
| CI Validation SQL | `masu/database/sql/openshift/cost_model/validate_rates_against_daily_summary.sql` | CI-only regression test: read-only comparison verifying aggregation correctness |
| Partition wiring | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | Call `get_or_create_partition()` before writing to `RatesToUsage` (not in `UI_SUMMARY_TABLES`) |
| Purge update | `masu/processor/ocp/ocp_report_db_cleaner.py` | Add `cost_model_rates_to_usage` to `purge_expired_report_data_by_date()` |
| DELETE for recalculation | `masu/database/ocp_report_db_accessor.py` | New `delete_rates_to_usage()` method — runs before each recalculation cycle |

### Validation

- `RatesToUsage` populated with per-rate rows at fine granularity
  (matching `usage_costs.sql` GROUP BY exactly)
- **CI validation test**: `validate_rates_against_daily_summary.sql`
  confirms aggregated `RatesToUsage` values match expected daily summary
  costs at the full (namespace, node, pod_labels, volume_labels,
  persistentvolumeclaim, all_labels, day) granularity
- Existing test suite passes — aggregation produces identical daily
  summary rows to the retired `usage_costs.sql` direct-write
- Performance benchmark: query time on `RatesToUsage` AND the
  aggregation query for a tenant with 30 rates, 100 namespaces, 30 days
  of data. The JSONB columns in the aggregation GROUP BY should be
  benchmarked specifically (see risk R13). Use
  [`poc/estimate_rates_to_usage_rows.sql`](./poc/estimate_rates_to_usage_rows.sql)
  for baseline estimates (note: estimates are lower bounds — actual row
  counts will be higher with fine-grained granularity).

### R2/R3 Mitigation — Phase 2 Benchmarking Plan

#### Why DELETE+INSERT aggregation (and not another approach)

The aggregation step replaces `usage_costs.sql` direct-write. There
are three possible aggregation patterns:

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | **UPDATE existing rows** — match pre-existing daily summary rows by composite key and set `cost_model_*_cost` columns | No new rows created. Simpler conceptually. | `usage_costs.sql` does not UPDATE — it creates *new* rows with `cost_model_rate_type = 'Infrastructure'/'Supplementary'` and `uuid_generate_v4()`. There are no pre-existing rows to UPDATE because the rate-type rows only exist after cost model processing. An UPDATE approach would require inventing a matching key for rows that don't exist yet. | **Rejected** — no target rows to update |
| B | **DELETE + INSERT** — delete existing rate-type rows, then INSERT aggregated rows from `RatesToUsage` | Matches the exact pattern of `usage_costs.sql` (which also does DELETE then INSERT). Downstream pipeline (distribution, UI summary) sees the same row structure. Conceptually clean: aggregation replaces the direct-write, so the mechanism is identical. | Two SQL statements per aggregation cycle. DELETE can be expensive on large partitions. | **Selected** |
| C | **UPSERT (INSERT ON CONFLICT)** — define a unique constraint on the rate-type rows and use `ON CONFLICT DO UPDATE` | Single statement. Avoids DELETE overhead. | The daily summary has no unique constraint on rate-type rows. Adding one would require a composite key on `(usage_start, cluster_id, namespace, node, data_source, persistentvolumeclaim, label_hash, cost_model_rate_type)` — an 8-column unique index that duplicates the existing primary key pattern and adds write overhead to all daily summary operations (not just cost model). | **Rejected** — invasive schema change to a core table |

**Why Option B**: `usage_costs.sql` has always used DELETE + INSERT to
write rate-type rows into the daily summary. The aggregation step is a
direct replacement for `usage_costs.sql`, so it should use the same
mechanism. This means distribution SQL, UI summary SQL, and all
downstream consumers see *exactly* the same row structure they expect.
Any difference in mechanism (UPDATE, UPSERT) would introduce subtle
compatibility risks with the 12+ downstream SQL files.

#### Why these benchmark thresholds

Before declaring Phase 2 complete, run these benchmarks against a
staging environment with realistic data. Use the largest available
tenant (or synthetic data matching production scale).

**Test configuration**: 30 rate types configured, 100 namespaces,
1000 nodes, 30 days of data, varying `pod_labels` cardinality.

The thresholds below are derived from koku's existing performance
envelope. Current `usage_costs.sql` processing completes in seconds for
typical tenants and < 60 seconds for the largest. Since the new pipeline
adds a RatesToUsage INSERT *and* an aggregation step (two queries
instead of one), we allow 2× the existing budget: 60s INSERT + 30s
aggregation = 90s vs current ~60s. The 5-minute end-to-end threshold
accounts for all steps (including distribution and UI summary, which
are unchanged).

| # | Benchmark | Acceptance Criteria | Risk |
|---|-----------|-------------------|------|
| 1 | `RatesToUsage` row count per month | < 100M rows/month (based on [`poc/estimate_rates_to_usage_rows.sql`](./poc/estimate_rates_to_usage_rows.sql) × fine-grained multiplier) | R3 |
| 2 | `insert_usage_rates_to_usage.sql` execution time | < 60 seconds per (source, rate_type, date range) | R3 |
| 3 | `aggregate_rates_to_daily_summary.sql` execution time | < 30 seconds per (source, date range) | R2, R13 |
| 4 | CI validation query: zero diff rows | All diffs = 0 (within NUMERIC precision) | R2 |
| 5 | `label_hash` index effectiveness | `EXPLAIN ANALYZE` shows index scan on `ratestousage_label_hash_idx` in aggregation | R13 |
| 6 | Markup ORM method processing time | < 30 seconds per (source, date range). If exceeded, switch to SQL fallback (R17). | R17 |
| 7 | End-to-end cost model update time | < 5 minutes per source (including distribution + UI summary) | R2, R3 |
| 8 | Partition size on disk | < 2 GB per monthly partition for `cost_model_rates_to_usage` | R3 |

**If any benchmark fails**: Investigate and document findings before
proceeding to Phase 3. Key levers: reduce `pod_labels` cardinality
via hash-based grouping, optimize indexes, or adjust the fine-grained
columns to use `label_hash` only (dropping raw JSONB from GROUP BY).

### Rollback

1. Revert new SQL files (`insert_usage_rates_to_usage.sql`,
   `aggregate_rates_to_daily_summary.sql`) and orchestration code
2. Restore `usage_costs.sql` direct-write call in the orchestration
   (`self._update_usage_costs(...)`) — the file itself is unchanged
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
Each SQL file gains a RatesToUsage INSERT alongside its existing daily
summary INSERT. Aggregation (from Phase 2) already populates the daily
summary from `RatesToUsage`.

**Trino dialect note**: The 8 `trino_sql/` files must use catalog-qualified
table names for the `RatesToUsage` INSERT (e.g.,
`INSERT INTO postgres.{{schema | sqlsafe}}.cost_model_rates_to_usage`). The 8
`self_hosted_sql/` files use standard PostgreSQL syntax since they execute
against PostgreSQL via Django. See
[sql-pipeline.md § Trino/Self-Hosted Architecture](./sql-pipeline.md#trinoself-hosted-architecture).

### Validation

- All cost types flow through `RatesToUsage` (usage, monthly, tag-based)
- Aggregation (from Phase 2) continues to produce correct daily summary
  rows with the additional cost types flowing through `RatesToUsage`
- Distributed costs calculated correctly (distribution SQL is unchanged
  but verify end-to-end — it reads from aggregation output)
- Full regression: compare total costs per tenant before/after
- Tag-based costs: verify `custom_name` attached correctly (one name per
  rate, not per tag value)

### R6 Mitigation — SQL File Testing Checklist

#### Why per-file-per-PR (and not another strategy)

| # | Approach | Pros | Cons | Verdict |
|---|----------|------|------|---------|
| A | **Single large PR** — modify all 25 SQL files in one PR | Ships Phase 3 in one merge. Easier to coordinate cross-file changes. | Impossible to review thoroughly: 25 SQL files × 3 paths = 75 file changes. A single bug can hide among hundreds of changed lines. Rollback is all-or-nothing — cannot revert one file without reverting all. Testing is coarse: hard to attribute a regression to a specific file. | **Rejected** — review quality degrades, rollback is blunt |
| B | **Per-path batches** — one PR per SQL path (PostgreSQL, Trino, self-hosted) | 3 PRs instead of 25. Each PR targets one execution engine. | Still 8-9 files per PR. Trino and self-hosted files mirror each other, so separate PRs for each adds redundant review cycles. A bug in a PostgreSQL file is still buried among 8 other changes. | Viable but still too coarse for regression isolation |
| C | **Per-file-per-PR** — one SQL file per PR, with the 8-point checklist | Each PR is small and reviewable. Regressions are immediately attributable to a specific file. Rollback is surgical: revert one PR. Checklist ensures consistent quality. | 25 PRs is a high count. Creates merge overhead. Some files are trivial (identical pattern). | **Selected** |
| D | **Grouped by cost type** — one PR per cost type (usage, monthly, tag, VM) | Logical grouping. 4-5 PRs. | Groups cross all 3 SQL paths. A Trino dialect bug in a tag file is mixed with a PostgreSQL tag file change. Harder to isolate path-specific issues. | **Rejected** — mixes execution engines |

**Why Option C**: The primary risk in Phase 3 is that one bad SQL file
breaks cost calculation silently (wrong `custom_name`, wrong
`metric_type`, wrong `calculated_cost`). Per-file PRs make each change
independently reviewable, testable, and revertable. The 25-PR overhead
is acceptable because: (1) each PR is small (one SQL file + one test),
(2) the checklist standardizes review, and (3) Phase 3 is not
time-critical — it can run in parallel with Phase 4 frontend work.

Trivially identical files (e.g., `infrastructure_tag_rates.sql` and
`supplementary_tag_rates.sql` which differ only in cost type) can be
combined into one PR if the reviewer agrees they are structurally
identical.

Each of the 25 SQL files must pass these checks before merging:

| # | Check | How |
|---|-------|-----|
| 1 | `RatesToUsage` INSERT produces expected row count | `SELECT COUNT(*)` with known cost model configuration |
| 2 | `custom_name` matches the `Rate.custom_name` for the rate being processed | Spot-check first 10 rows |
| 3 | `metric_type` is correct for the rate (cpu/memory/storage/gpu) | `SELECT DISTINCT metric_type` |
| 4 | `calculated_cost` matches the existing daily summary value for that rate | CI validation query (from Phase 2) |
| 5 | `label_hash` is populated and matches `md5(pod_labels \|\| volume_labels \|\| all_labels)` | `SELECT COUNT(*) WHERE label_hash IS NULL` = 0 |
| 6 | Aggregation output unchanged after adding the file | Compare daily summary totals before/after |
| 7 | Trino dialect correct (catalog-qualified names, `uuid()`, `CAST`) | Run against Trino-enabled dev environment |
| 8 | Self-hosted variant uses PostgreSQL syntax | Run against PostgreSQL directly |

**Ordering**: PostgreSQL path first (lower risk), then Trino, then
self-hosted (mirrors Trino). Tag-rate files before monthly-cost files
(simpler modifications first).

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
| Breakdown population SQL | `masu/database/sql/openshift/ui_summary/reporting_ocp_cost_breakdown_p.sql` | Populate from `RatesToUsage` (per-rate) + daily summary (distribution back-allocation per IQ-9) with tree paths |
| Back-allocation SQL (IQ-9) | Part of `reporting_ocp_cost_breakdown_p.sql` | Split distribution `distributed_cost` into per-rate shares using `RatesToUsage` proportions. See [sql-pipeline.md](./sql-pipeline.md#back-allocation-sql-sketch) |
| `UI_SUMMARY_TABLES` update | `reporting/provider/ocp/models.py` | Add to tuple for partition cleanup |
| Provider map entry | `api/report/ocp/provider_map.py` | `cost_breakdown` report type |
| View class | `api/report/ocp/view.py` | `OCPCostBreakdownView` |
| Serializers | `api/report/ocp/serializers.py` | `CostBreakdownFlatItemSerializer` + `CostBreakdownTreeNodeSerializer` (IQ-3) |
| URL registration | `api/urls.py` | `breakdown/openshift/cost/` |
| Frontend: report type | `api/reports/report.ts` | `ReportType.costBreakdown` |
| Frontend: API path | `api/reports/ocpReports.ts` | `breakdown/openshift/cost/` |
| Frontend: flat list | `routes/details/components/costOverview/` | `CostBreakdownTable` component |
| Frontend: tab restructure | `routes/details/components/breakdown/breakdownBase.tsx` | Move usage cards to "Usage overview" tab |
| Frontend: export | `api/export/ocpExport.ts` | Breakdown CSV export |

### Validation

- Breakdown table populated correctly (spot-check against `RatesToUsage`)
- Back-allocation correctness: `SUM(per-rate distributed_cost)` per
  (namespace, node, day, distribution_type) equals the original
  `distributed_cost` row from the daily summary (rounding tolerance:
  < $0.01)
- API returns expected flat/tree structure (compare with PRD examples)
- API returns both flat and tree views correctly (`?view=flat`, `?view=tree`)
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

**Goal**: Remove legacy JSON rate storage path and dead `usage_costs.sql`
direct-write code.

### Artifacts

| Artifact | File | Description |
|----------|------|-------------|
| Migration M6 | `cost_models/migrations/XXXX_drop_rates_json.py` | `ALTER TABLE cost_model DROP COLUMN rates` |
| Remove dual-write | `cost_models/serializers.py` | API writes to Rate table only |
| Remove JSON read path | `masu/database/cost_model_db_accessor.py` | Remove `_price_list_from_json()` fallback |
| Remove `usage_costs.sql` direct-write | `masu/database/sql/openshift/cost_model/usage_costs.sql`, `ocp_report_db_accessor.py` | Dead code since Phase 2 aggregation took over. Remove the direct-write INSERT and its orchestration call. |
| Remove validation SQL | `masu/database/sql/openshift/cost_model/validate_rates_against_daily_summary.sql` | No longer needed once aggregation is the only path. Can be retained as a CI-only test if desired. |

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
| R2 | Aggregation step produces different values than direct-write (rounding, NULLs, missing rows) | HIGH | MEDIUM | 2 | **RESOLVED (OQ-3)**: CI validation query compares at fine granularity using `label_hash` JOIN (R13). Phase 2 benchmarking plan requires zero-diff validation (benchmark #4). Fine-grained columns on `RatesToUsage` resolve the granularity mismatch (IQ-1). |
| R3 | Row explosion in `RatesToUsage` causes query timeouts | MEDIUM | MEDIUM | 2 | 12x multiplier quantified (OQ-1). Fine-grained granularity increases row counts beyond the original 36M/month estimate. **Mitigated**: Phase 2 benchmarking plan (benchmarks #1, #2, #7, #8) with concrete acceptance criteria. Partition by month. `label_hash` index (R13) reduces aggregation cost. |
| R4 | Monthly cost rates produce more rows than expected (per-namespace allocation) | ~~MEDIUM~~ **MITIGATED** | ~~HIGH~~ LOW | 3 | **RESOLVED (OQ-2)**: GROUP BY is `(usage_start, source_uuid, cluster_id, node, namespace, pod_labels, cost_category_id)`. Row count per monthly rate quantifiable from existing data. |
| R5 | Cost category reclassification invalidates breakdown tree | ~~MEDIUM~~ **MITIGATED** | ~~LOW~~ NONE | 4 | **RESOLVED (OQ-4)**: `CostGroupsAddView`/`CostGroupsRemoveView` already trigger `update_summary_tables` which chains into full cost model recomputation. No special handling needed. |
| R6 | 25 SQL file modifications across 3 paths introduce regressions | MEDIUM | MEDIUM | 3 | **Mitigated**: 8-point testing checklist per SQL file (see Phase 3 § R6 Mitigation). Modify one file per PR; PostgreSQL path first, then Trino, then self-hosted. |
| R7 | Dual-write divergence (JSON and Rate table drift) | LOW | LOW | 1-4 | `_sync_rate_table` does delete-all + recreate on every write; no partial sync |
| R8 | `custom_name` migration produces ugly names for rates with empty descriptions | LOW | HIGH | 1 | Acceptable per PRD ("ugly but functional"); users can rename after migration |
| R9 | Frontend tab restructure breaks existing user workflows | LOW | LOW | 4 | Usage cards move to adjacent tab, not removed; link/breadcrumb from old location |
| R10 | Trino SQL dialect requires catalog-qualified table names for `RatesToUsage` INSERT | MEDIUM | MEDIUM | 3 | Test `trino_sql/` files with Trino locally; `self_hosted_sql/` files use standard PostgreSQL syntax and are lower risk |
| R11 | Concurrent cost model updates with overlapping date ranges create duplicate `RatesToUsage` rows | MEDIUM | LOW | 2-3 | Existing Redis lock (`WorkerCache.lock_single_task`) prevents identical `(schema, provider, start, end)` runs; DELETE-before-INSERT pattern (Step 0) clears stale rows per recalculation window; risk is limited to rare overlapping-range scenarios |
| R12 | `CostModelManager.update()` has no `@transaction.atomic` — dual-write (JSON save + Rate table sync) can partially fail | MEDIUM | MEDIUM | 1 | Add `@transaction.atomic` to `update()`. `create()` already has it. See [api-and-frontend.md](./api-and-frontend.md). |
| R13 | JSONB column equality JOINs in aggregation/validation SQL are slow on large datasets | ~~HIGH~~ **MITIGATED** | ~~MEDIUM~~ LOW | 2 | **MITIGATED**: `label_hash` column (`md5(pod_labels::text \|\| volume_labels::text \|\| all_labels::text)`) added to `CostModelRatesToUsage` model and DDL. Computed during INSERT, indexed via B-tree (`ratestousage_label_hash_idx`). Aggregation GROUP BY and validation JOIN use `label_hash` instead of 3 JSONB equality comparisons. Phase 2 benchmark #5 verifies index effectiveness. See [data-model.md](./data-model.md) and [sql-pipeline.md](./sql-pipeline.md). |
| R14 | Back-allocation rounding: proportional split of `distributed_cost` to per-rate shares may produce minor rounding differences | LOW | HIGH | 4 | **MITIGATED**: Reconciliation check SQL added to [sql-pipeline.md § R14 Mitigation](./sql-pipeline.md#r14-mitigation--rounding-reconciliation-check). Post-INSERT query compares `SUM(per-rate shares)` vs original `distributed_cost`; discrepancies > $0.01 are logged. `NUMERIC(33, 15)` precision makes this extremely unlikely. |
| R15 | Back-allocation JOIN complexity: matching distribution rows to source namespace costs and `RatesToUsage` proportions requires multi-table CTEs | MEDIUM | MEDIUM | 4 | The back-allocation SQL has 3 CTEs with JOINs across daily summary and `RatesToUsage`. **Mitigation**: (1) Benchmark with realistic data in Phase 4; (2) Source cost and rate_shares CTEs operate on source namespaces (small cardinality — typically 1 Platform namespace per cluster); (3) Indexes on `(usage_start, cluster_id, source_uuid)` cover the JOIN paths. |
| R16 | Aggregation GROUP BY granularity mismatch: `RatesToUsage` does not include `resource_id` (matching `usage_costs.sql` GROUP BY) but the daily summary has `resource_id`. If future SQL changes add `resource_id` to the daily summary's cost model rows, the aggregation SQL must be updated to match. | LOW | LOW | 2 | The PoC and IQ-5 CTE confirm `usage_costs.sql` does not GROUP BY `resource_id`. The aggregation SQL sketch has been aligned. **Mitigation**: document that `resource_id` is not part of the cost model GROUP BY in the aggregation, and add a regression test confirming no `resource_id`-based row splitting. |
| R17 | Markup → RatesToUsage uses Python ORM iterator + `bulk_create` to copy daily summary markup rows. For large tenants, this is slower and more memory-intensive than a SQL-based approach. | LOW | MEDIUM | 2 | **MITIGATED**: SQL-based fallback (`insert_markup_rates_to_usage.sql`) designed in [sql-pipeline.md](./sql-pipeline.md#markup--ratestousage-step-2). Phase 2 benchmark #6 tests ORM method; switch to SQL if > 30s. `bulk_create(batch_size=5000)` limits memory for ORM path. |

### Risk × Phase Matrix

```
          Phase 1    Phase 2    Phase 3    Phase 4    Phase 5
R1          ✓          ✓ (mitigated — OQ-1 resolved)
R2                     ██ (aggregation replaces direct-write)
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
R13                    ✓ (mitigated — label_hash replaces JSONB GROUP BY)
R14                                         ██ (back-allocation rounding)
R15                                         ██ (back-allocation JOIN complexity)
R16                    ██ (aggregation GROUP BY granularity)
R17                    ██         ██ (markup ORM overhead)
```

---

## Future Scalability Considerations

The single-source-of-truth architecture (RatesToUsage → aggregation →
daily summary) was chosen in part because it scales better with two
upcoming features that will increase the rate calculation surface area.

### Price List Lifecycles

Multiple price lists per cost model means more rate calculations per
processing cycle. With a single source of truth, each additional price
list adds rows to `RatesToUsage` and the aggregation step folds them
into the daily summary automatically. A dual-path approach would
require updating both `usage_costs.sql` (direct-write) and the
`RatesToUsage` INSERT for every new price list configuration.

### Consumer and Provider

Multiple cost models applying to the same data multiplies the rate
calculation volume. The single-source-of-truth architecture handles
this naturally — each cost model writes its per-rate rows to
`RatesToUsage`, and aggregation produces the correct daily summary
totals. Dual-path maintenance overhead would compound with each
additional cost model.

### Architectural benefit

With the single calculation point in `RatesToUsage`, changes to rate
logic propagate automatically to both the daily summary (via
aggregation) and the breakdown table. QE validates cost correctness
once against the daily summary, rather than maintaining parallel
verification of two independent calculation paths across an expanding
set of rate configurations.

---

## Timeline Considerations

Phase 1 can start immediately — it has no open questions. The
`_price_list_from_rate_table()` format compatibility has been validated
by PoC tests ([`poc/price_list_compat.py`](./poc/price_list_compat.py),
6/6 pass).

Phase 2 is **unblocked** — all four open questions (OQ-1 through OQ-4)
have been resolved via source code triage, and IQ-1 has been confirmed
by the tech lead (single source of truth via aggregation, no dual-path).
The RatesToUsage INSERT SQL has been prototyped
([`poc/insert_usage_rates_to_usage.sql`](./poc/insert_usage_rates_to_usage.sql)).
Implementation can proceed immediately after Phase 1 ships. Key Phase 2
risk to monitor: R13 (JSONB column performance in aggregation).

Phases 3 and 4 can overlap: Phase 3 SQL changes are independent of
Phase 4 API/frontend work, as long as Phase 2 is complete. The
breakdown table population SQL has been prototyped
([`poc/reporting_ocp_cost_breakdown_p.sql`](./poc/reporting_ocp_cost_breakdown_p.sql)).

Phase 5 should only run after Phase 4 has been validated in production
for a sufficient period (recommended: at least one full billing cycle).

### Blocking dependencies

```
Phase 1 ← no blockers (start now)
Phase 2 ← Phase 1 (IQ-1 confirmed — single source of truth, no dual-path)
Phase 3 ← Phase 2 + R13 benchmark acceptable
Phase 4 ← Phase 3 (IQ-3 confirmed — flat DB rows, both API formats)
Phase 5 ← Phase 4 validated in production
```

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-17 | Initial: 5-phase delivery plan, artifact lists per phase, validation criteria, rollback strategies, risk register (R1-R12), risk × phase matrix, timeline and blocking dependencies. |
| v2.0 | 2026-03-17 | IQ-1 resolved: rewrite Phase 2 artifacts (usage_costs.sql replaced, validate moved to CI-only). Remove dual-path validation references. Update risk register (R2, R3 revised, R13 added). Update blocking dependencies. |
| v2.2 | 2026-03-17 | IQ-3/IQ-7 resolved, IQ-9 added: update decisions table. Add back-allocation SQL to Phase 4 artifacts and validation. Add risks R14 (rounding) and R15 (JOIN complexity). Add "Future Scalability Considerations" section. |
| v2.3 | 2026-03-17 | Blast-radius triage: fix Phase 4 serializer reference (two serializers, not one). Add R16 (aggregation GROUP BY granularity) and R17 (markup ORM overhead). Update risk × phase matrix. |
| v2.4 | 2026-03-17 | Risk mitigation: R13 downgraded to MITIGATED (label_hash). R6 — add 8-point SQL testing checklist for Phase 3. R2/R3 — add Phase 2 benchmarking plan with 8 acceptance criteria. Update R2, R3, R6, R14, R17 mitigation descriptions in risk register. |
| v2.5 | 2026-03-17 | Decision rationales: add alternatives-evaluated tables for R6 (per-file-per-PR, 4 options) and R2/R3 (DELETE+INSERT aggregation, 3 options + threshold derivation). |
