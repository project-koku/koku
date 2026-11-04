# RTU hardening: test plan

Branch `mpovolny/rtu-hardening` (draft PR [#6425](https://github.com/project-koku/koku/pull/6425), image builds only). Covers work log items 1, 1b, 1c, 2 and 3 of [`rtu-race-map.md`](rtu-race-map.md); later items add their rows here. How to run everything: [`README.md`](README.md).

Out of scope: correctness of the cost breakdown API and of the breakdown tree itself. That is the QE plan "Cost Breakdown and Rate Filtering" (`docs/tests/COST-7249/qe-test-plan-cost-breakdown.md`, added by #6102). Phase 1 schema normalization (Rate table, diff-based `sync_rate_table`, write freeze) is `docs/architecture/cost-breakdown/test-plan.md`.

## What changed

| Item | Change |
|---|---|
| 1 | `rates_to_usage.rate_id` and `.cost_model_id` have no FK constraint and no cascade (migration `0355`, model `DO_NOTHING` + `db_constraint=False`) |
| 1b | Deleting rates (`sync_rate_table`, `PriceListManager.delete`) or a cost model schedules `delete_rates_to_usage_rows` on commit; the task deletes their RTU rows in every month |
| 1c | Per-rate distributed RTU rows (platform, worker, unattributed storage and network, GPU) carry the source row's `rate_id`; negation and infra-only rows keep `rate_id = NULL` |
| 2 | A price list PUT saves the price list and syncs its Rate rows in one transaction; a cost model PUT changes sources and rates in one transaction |
| 3 | `rates_to_usage` has no FK at all to its report period or source (migration `0356`); `Provider.delete()` and both OCP retention purges delete its rows explicitly first |

## Invariants

| ID | Invariant |
|---|---|
| I1 | Deleting a Rate or CostModel never deletes from or scans `rates_to_usage` inside the API request |
| I2 | A pipeline insert that carries a deleted rate's UUID (or an unknown cost model UUID) succeeds |
| I3 | After a rate is deleted, no RTU row with its `rate_id` remains, in any month, including distributed rows |
| I4 | After a cost model is deleted, no RTU row with its `cost_model_id` remains, in any month |
| I5 | A cleanup is scheduled only when the delete commits, and only when something was deleted |
| I6 | Distribution results are unchanged by 1c: same totals; each per-rate distributed row has its source row's (`custom_name`, `rate_id`); negation rows have no `rate_id` |
| I7 | Superseded by I10 (item 3): no RTU FK cascades in the database |
| I8 | Rows of rates that still exist are never deleted by the cleanup |
| I9 | A failed rate sync leaves the price list or cost model exactly as before: name, version, rates JSON, source mapping, and no recalculation dispatched |
| I10 | Deleting a provider, or purging report periods by provider or by date, removes exactly their RTU rows (in every partition) and no others; inserts referencing a missing source or report period succeed |

## Unit tests (local, `koku-db` on :15432)

```bash
python koku/manage.py test --noinput reporting.provider.ocp.test.test_rtu_migrations \
  masu.test.processor.test_delete_rates_to_usage_rows cost_models.test.test_rtu_cleanup \
  masu.test.processor.ocp.test_phase4_distribution cost_models.test.test_atomic_updates \
  reporting.provider.ocp.test.test_rtu_parent_deletes masu.test.processor.ocp.test_ocp_report_db_cleaner
```

| Test | Invariants | Red before the fix |
|---|---|---|
| `test_rtu_migrations.test_rate_and_cost_model_columns_have_no_constraint` | I1, I7 | yes |
| `test_rtu_migrations.test_rate_delete_keeps_rtu_rows`, `test_cost_model_delete_keeps_rtu_rows` | I1 | yes |
| `test_rtu_migrations.test_insert_with_deleted_rate_id_succeeds`, `test_insert_with_unknown_cost_model_id_succeeds` | I2 | yes (`IntegrityError` on the FK) |
| `test_delete_rates_to_usage_rows.test_deletes_rows_of_deleted_rates_in_every_month` | I3, I8 | yes (task missing) |
| `test_delete_rates_to_usage_rows.test_deletes_rows_of_deleted_cost_models` | I4, I8 | yes |
| `test_delete_rates_to_usage_rows.test_no_ids_deletes_nothing` | I8 | yes |
| `test_rtu_cleanup.test_sync_rate_table_schedules_deleted_rates`, `test_price_list_delete_schedules_its_rates`, `test_cost_model_delete_schedules_cost_model` | I3, I4 | yes |
| `test_rtu_cleanup.test_sync_rate_table_without_deletes_schedules_nothing`, `test_rolled_back_delete_schedules_nothing` | I5 | yes |
| `test_phase4_distribution.test_12_recipient_rows_carry_source_rate_id` | I6 | yes |
| `test_phase4_distribution.test_13_rate_cleanup_removes_distributed_rows` | I3 (distributed) | yes |
| `test_atomic_updates.test_failed_sync_rolls_back_price_list_changes` | I9 | yes (price list stayed renamed) |
| `test_atomic_updates.test_failed_rate_update_rolls_back_source_changes` | I9 | yes (source mapping changed on a 400) |
| `test_rtu_parent_deletes.test_no_report_period_or_source_constraint`, `test_insert_with_unknown_report_period_and_source_succeeds` | I10 | yes |
| `test_rtu_parent_deletes.test_provider_delete_removes_its_rows_only`, `test_purge_by_provider_removes_its_rows_only`, `test_purge_by_date_removes_rows_of_expired_report_periods` | I10 | yes, after `0356` and before the explicit deletes |
| `test_ocp_report_db_cleaner.test_purge_expired_report_data_for_provider_deletes_rtu` (existing) | I10 | yes, same |
| `test_phase4_distribution` existing tests 01–11 (proportionality, sum consistency, cost conservation, sign, idempotency, multi-rate, two-phase equivalence) | I6 (totals) | n/a, must stay green |

Known local failures not caused by this work (identical on `main`): 15 tests in `masu.test.processor.ocp.test_phase2_rates_to_usage` and `test_phase4_distribution.test_worker_zero_rate_pool_is_distributed_and_negated_exactly` (work log item 8). `api.provider.test.test_provider_manager.test_provider_statistics` and `_ocp_on_cloud` fail when the cached test database predates the current month (no report period for it).

## Database-only measurement (local)

`testdata/seed_rtu.py` + `testdata/measure_rate_delete.sh`, see README. Verifies the reason for I1: with the cascade, deleting 30 rates over 1.8M RTU rows took 7,283 ms; without it, 1.1 ms (2026-11-03).

## End-to-end scenarios (ephemeral)

Setup: README "Ephemeral, end to end" (deploy with `SOURCES_BYPASS_RBAC=true`, flag on, `testdata.sh toolbox sources cost-models upload wait-rtu`). Data: 2 OCP clusters, previous month 1st to today, 16 rates in one price list shared by both cost models. Every check is `testdata.sh verify` plus the queries named.

| ID | Steps | Expected | Invariants |
|---|---|---|---|
| E1 Baseline | load data, `verify` | tenant on `0355`; FKs only `report_period_id`, `source_uuid` (cascade) and `cost_category_id`; RTU rows for both clusters in both months; 0 rows pointing to a deleted rate; every distributed type has 0 per-rate rows without `rate_id` (includes Trino-written `gpu_distributed`) | I6, I7 |
| E2 Remove rates | `testdata.sh remove-rate <name>` for one rate of each writer: `cpu_core_usage_per_hour-Supplementary` (usage), `node_cost_per_month-Infrastructure` (monthly, `rate_uuid` parameter), `vm_cost_per_hour-Supplementary` (VM, Trino), `gpu_cost_per_month-Infrastructure-nvidia` (GPU, Trino distribution); `verify` | `delete_rates_to_usage_rows` in the cost-model worker log within seconds of each PUT; 0 rows of the removed rates in **both** months, distributed rows included; other rates' rows unchanged | I3, I8 |
| E3 Recalculation after E2 | wait for the dispatched recalculation, `verify` | current month rebuilt without the removed rates; no failed `update_cost_model_costs` | I2 |
| E4 Delete a cost model | `DELETE /cost-models/<uuid>/` for one cluster, `verify` | 0 RTU rows with that `cost_model_id` in both months; the other cluster untouched | I4, I8 |
| E5 Delete an unassigned price list | create a second price list with a rate, never assign it, delete it | cleanup task scheduled with its rate IDs; no error | I3, I5 |
| E6 Remove a rate during a running recalculation | start a recalculation (`update_cost_model_costs` for the previous month), remove a rate while it runs | the run completes without `IntegrityError`. Known limitation: rows the run writes for the removed rate after the cleanup stay until that month is recalculated again | I2 |
| E7 Rebuild cleans its window | re-upload the data after E2 | reprocessed months contain no rows of the removed rates | I3 |
| E8 Delete a source | delete one cluster's source through sources-api, wait for the provider delete, `verify` | tenant on `0356`; no RTU FKs except `cost_category_id`; 0 RTU rows of the deleted source; the other cluster untouched | I10 |

## Results

| Run | Image | Result |
|---|---|---|
| 2026-11-03, `ephemeral-7ctbkc` | `pr-6425-a5c7320` (items 1, 1b) | E1 pass; E2 pass for `rate_id` rows (1,734 / 1,156 / 306 rows deleted in about 25 ms each); 2,232 distributed rows without `rate_id` survived in the previous month (found item 1c); E3 pass; E7 pass (rebuild removed them). Details: README "Results" |
| 2026-11-04, `ephemeral-wufsxu` | `pr-6425-0da7c0b` (items 1, 1b, 1c) | E1 pass: both clusters October 23,622 / November 3,020 rows, 13 rates; distributed rows with `rate_id`: gpu 248 (Trino template), platform 10,080, worker 8,820, without: 0. E2 pass: removed usage, monthly, VM and GPU rates; cleanup deleted 6,090 / 4,900 / 594 / 3,118 rows (now including distributed rows) in 19-31 ms; 0 rows of the removed rates in either month. E3 pass: 6 recalculations succeeded, 0 errors; both clusters November 9 identical rates. E4 pass: deleting cluster A's cost model deleted 19,273 rows (its whole RTU, both months); cluster B untouched. E5 pass: deleting an unassigned price list scheduled the cleanup with its 1 rate ID (0 rows), no error |

E6 on `ephemeral-wufsxu` (`testdata.sh e6`, October recalculation of cluster B, rate removed DELAY seconds later): two attempts, both runs succeeded with 0 orphan rows and no `IntegrityError`, but neither hit the race window: with DELAY=5 the monthly insert (09:09:17.1) came before the removal and the cleanup deleted its rows (2,450); with DELAY=0.3 the run loaded the rates after the removal ("removing monthly cost [OCP_VM]"). The window between `_load_rates()` and the monthly insert is about 1 s; hitting it end to end needs an injected delay (like the "Path B" of the COST-81xx tickets). I2 is covered deterministically by `test_insert_with_deleted_rate_id_succeeds`. E7 on this image has not been run.

## Regression: existing IQE tests to run against the branch

From `iqe-cost-management-plugin` (`iqe_cost_management/tests/rest_api/v1/`):

- `test__i_source_f_ocp_price_lists.py`: `test_api_ocp_source_raw_price_list_recalc_logic`, `test_api_ocp_source_raw_price_list_recalc_negative`, `test_api_ocp_sources_multiple_rates`, `test_api_ocp_sources_shared_rates_recalculation`
- `test_price_lists.py` (price list CRUD)

These exercise rate changes and recalculation through the API. They do not read RTU, so they guard behaviour, not the invariants above.

## For QE (candidate IQE tests)

With the RTU flag on: E2 (rows of a removed rate disappear in every month, including distributed rows), E4 (cost model delete), and E3 (recalculation after a rate removal does not fail). They need a read path for RTU state, which today only the database offers; with #6102 merged, the breakdown API is that path.

## Not covered yet

- Rows written by a pipeline run that races a provider delete stay until retention drops their partitions (no FK rejects them any more).

- Trino templates are exercised only in ephemeral (no Trino in unit tests).
- On-prem (`ONPREM=True`) end to end; the self-hosted GPU template is covered only by the unit tests.
- The price list API returns no `rate_id` (item 9), so a rename is delete + create.
