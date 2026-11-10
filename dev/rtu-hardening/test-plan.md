# RTU hardening: test plan

Branch `mpovolny/rtu-hardening` (draft PR [#6425](https://github.com/project-koku/koku/pull/6425), image builds only). Covers work log items 1 to 7 and 9 of [`rtu-race-map.md`](rtu-race-map.md); later items add their rows here. How to run everything: [`README.md`](README.md).

Out of scope: correctness of the cost breakdown API and of the breakdown tree itself. That is the QE plan "Cost Breakdown and Rate Filtering" (`docs/tests/COST-7249/qe-test-plan-cost-breakdown.md`, added by #6102). Phase 1 schema normalization (Rate table, diff-based `sync_rate_table`, write freeze) is `docs/architecture/cost-breakdown/test-plan.md`.

## What changed

| Item | Change |
|---|---|
| 1 | `rates_to_usage.rate_id` and `.cost_model_id` have no FK constraint and no cascade (migration `0355`, model `DO_NOTHING` + `db_constraint=False`) |
| 1b | Deleting rates (`sync_rate_table`, `PriceListManager.delete`) or a cost model schedules `delete_rates_to_usage_rows` on commit; the task deletes their RTU rows in every month |
| 1c | Per-rate distributed RTU rows (platform, worker, unattributed storage and network, GPU) carry the source row's `rate_id`; negation and infra-only rows keep `rate_id = NULL` |
| 2 | A price list PUT saves the price list and syncs its Rate rows in one transaction; a cost model PUT changes sources and rates in one transaction |
| 3 | `rates_to_usage` has no FK at all to its report period or source (migration `0356`); `Provider.delete()` and both OCP retention purges delete its rows explicitly first |
| 5 | Retention purges by date drop expired partitions with one statement per parent table (all four providers) |
| 6 | `GET /price-lists/<uuid>/rates/` never writes and matches JSON to Rate rows read-only; `sync_rate_table` keeps Rate identity and names for JSON without `rate_id` / `custom_name` |
| 4 | Every RTU writer runs under `_distribution_provider_lock(provider)` for its whole delete-and-insert sequence when it writes RTU |
| 9 | `GET /price-lists/<uuid>/rates/` no longer returns `rate_id`; `custom_name` is the only rate identity in the API (FedRAMP CM-7) |
| 7 | `docs/specs/openapi.json` documents the price list rates and duplicate endpoints and the list parameters the API accepts |

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
| I11 | A purge by date never holds ACCESS EXCLUSIVE on two parent tables at once: one autocommitted statement per table, dropping exactly the expired non-default partitions of the listed tables |
| I12 | The rates GET issues no write statements and returns the same rates (names, tiered and tag rates) whether or not the JSON carries `rate_id` / `custom_name`; Rate UUIDs stay stable (I13) |
| I13 | Syncing JSON without `rate_id` / `custom_name` (the pre-0013 shape) keeps every Rate's UUID and name |
| I14 | Two overlapping RTU writes for one provider leave exactly the rows of one run (no double counting); legacy (`use_rtu=False`) writes take no lock |
| I15 | No API response carries `rate_id`: the price list and cost model rates (#6123) and `GET /price-lists/<uuid>/rates/` |
| I16 | The OpenAPI spec matches the price list API: documented response fields cover what the rates endpoint returns, no rate identifier is documented, and every documented query parameter is accepted |

## Unit tests (local, `koku-db` on :15432)

```bash
python koku/manage.py test --noinput reporting.provider.ocp.test.test_rtu_migrations \
  masu.test.processor.test_delete_rates_to_usage_rows cost_models.test.test_rtu_cleanup \
  masu.test.processor.ocp.test_phase4_distribution cost_models.test.test_atomic_updates \
  reporting.provider.ocp.test.test_rtu_parent_deletes masu.test.processor.ocp.test_ocp_report_db_cleaner \
  koku.test.test_drop_expired_partitions cost_models.test.test_price_list_view \
  masu.test.database.test_rtu_writer_lock
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
| `test_drop_expired_partitions.test_one_statement_per_parent_table` | I11 | yes (1 statement for 2 tables) |
| `test_drop_expired_partitions.test_drops_only_expired_partitions_of_listed_tables`, `CleanersUseDropExpiredPartitionsTest` (OCP, AWS, Azure, GCP) | I11 | the cleaner tests yes (helper missing) |
| `test_price_list_view.test_rates_endpoint_reads_without_writes_when_rate_id_missing` (replaces TC-124) | I12 | yes (UUIDs changed, writes issued) |
| `test_price_list_view.test_sync_rate_table_keeps_rates_of_json_without_rate_id` | I13 | yes (every Rate replaced, `-2` names) |
| `test_price_list_view.test_match_rates_to_json_*` (replace TC-112 to TC-114) | I12 | yes (function missing) |
| `test_rtu_writer_lock.test_overlapping_windows_do_not_double_rows` | I14 | yes (32 rows instead of 16) |
| `test_rtu_writer_lock.RatesToUsageWriterLockDecoratorTest` (RTU locks, legacy does not, all seven writers wrapped) | I14 | yes (decorator missing) |
| `test_price_list_view.test_rates_endpoint_does_not_expose_rate_id` | I15 | yes (`rate_id` in every entry) |
| `test_price_list_view.test_rates_response_matches_openapi_schema` | I16 | yes (path and schema missing) |
| `test_price_list_view.test_documented_query_parameters_are_accepted` | I16 | yes (`name`, `uuid`, `enabled`, `ordering` returned 400) |
| `test_phase4_distribution` existing tests 01–11 (proportionality, sum consistency, cost conservation, sign, idempotency, multi-rate, two-phase equivalence) | I6 (totals) | n/a, must stay green |

Local test runs: none fail. The failures listed here earlier (15 in `test_phase2_rates_to_usage`, the worker zero-rate test, the parquet summary updaters, provider statistics) came from a stale kept test DB built before the month changed; rebuilt with `KEEPDB=False`, the full suite passes (2026-11-04: 4,935 tests, 43 skipped). See `docs/agent/testing.md`. `koku.test_pg_partition.test_skips_locked_table_and_succeeds_later` is timing-sensitive (200 ms `lock_timeout`) and failed once in a combined run; it passed alone and in the full suite.

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
| E9 Overlapping recalculations (item 4) | `testdata.sh recalc` a serial window as baseline, then two overlapping windows on different queues (`priority`, `cost_model`) at once; `rtu-totals` | RTU rows and cost equal the baseline | I14 |
| E10 Rates endpoint and unnamed PUT (items 6, 9) | `rates-check`; `rate-ids`; `put-rates-unnamed`; `rate-ids`; `rates-check` | no `rate_id` in the response, tiered and tag rates present; Rate names and UUIDs unchanged by the PUT | I12, I13, I15 |
| E8 Delete a source | delete one cluster's source through sources-api, wait for the provider delete, `verify` | tenant on `0356`; no RTU FKs except `cost_category_id`; 0 RTU rows of the deleted source; the other cluster untouched | I10 |
| E11 Single-flight: overlapping runs serialize (S2, COST-8575) | flag `cost-management.backend.cost-model-single-flight` on (`FLAG=... deploy.sh flag`); baseline `rtu-totals` and the monthly-cost rows; then `recalc` the full month on `priority` and a sub-window on `cost_model` at the same time | the second updater starts only after the first run finished (worker log "updating cost model costs for provider"); RTU totals and monthly-cost rows equal the baseline | I8 |
| E12 Single-flight: busy month defers | `hold-run-lock 300 <month>` (holds the provider month's run lock), `recalc` that month 5 s later; `delayed-tasks`; wait for the `*/30` delayed-tasks beat | after the 2-minute wait the run logs "busy for provider month, deferring" and writes nothing; one `delayed_celery_tasks` row for the provider month with its window; the row fires on the beat and the run completes; totals equal the baseline | I8 |
| E13 Orphan sweep (S4) | insert RTU rows with an unknown `source_uuid` and an unknown `rate_id`; run `sweep_orphaned_rates_to_usage` (masu pod, `manage.py shell`) twice | first sweep deletes exactly the planted rows (1 source, 1 rate); second sweep deletes nothing; no other rows lost | I10 |

## Results

| Run | Image | Result |
|---|---|---|
| 2026-11-03, `ephemeral-7ctbkc` | `pr-6425-a5c7320` (items 1, 1b) | E1 pass; E2 pass for `rate_id` rows (1,734 / 1,156 / 306 rows deleted in about 25 ms each); 2,232 distributed rows without `rate_id` survived in the previous month (found item 1c); E3 pass; E7 pass (rebuild removed them). Details: README "Results" |
| 2026-11-04, `ephemeral-wufsxu` | `pr-6425-0da7c0b` (items 1, 1b, 1c) | E1 pass: both clusters October 23,622 / November 3,020 rows, 13 rates; distributed rows with `rate_id`: gpu 248 (Trino template), platform 10,080, worker 8,820, without: 0. E2 pass: removed usage, monthly, VM and GPU rates; cleanup deleted 6,090 / 4,900 / 594 / 3,118 rows (now including distributed rows) in 19-31 ms; 0 rows of the removed rates in either month. E3 pass: 6 recalculations succeeded, 0 errors; both clusters November 9 identical rates. E4 pass: deleting cluster A's cost model deleted 19,273 rows (its whole RTU, both months); cluster B untouched. E5 pass: deleting an unassigned price list scheduled the cleanup with its 1 rate ID (0 rows), no error |
| 2026-11-04, `ephemeral-wufsxu` redeployed | `pr-6425-341cb7b` (items 1-3) | tenant migrated in place to `0356`, only `cost_category_id` FK left on `rates_to_usage`. E8 pass (`testdata.sh delete-source rtu-cluster-b`): `Provider.delete()` deleted 16,415 RTU rows of cluster B (its October 14,539 + November 1,876) before the cascade delete, which completed 0.18 s later; 0 rows of B remain; cluster A's 1,876 rows unchanged |
| 2026-11-04, `ephemeral-wufsxu` redeployed | `pr-6425-2fde03a` (items 1-6, 9) | Items 6, 9: `testdata.sh rates-check` returned all 10 rates (6 tiered, 4 tag) and 0 entries with `rate_id`; `put-rates-unnamed` PUT all 10 rates without `custom_name` and every Rate name and UUID stayed the same (`rate-ids` before/after). Item 4: `recalc` baseline, serial October for cluster A: 14,539 RTU rows, cost 28,429.00; then Oct 1-31 on the `priority` worker (17:03:35.2-17:03:46.6) and Oct 1-15 on the `cost_model` worker (17:03:38.0-17:03:51.4) in parallel, their RTU writers active in the same seconds: October still 14,539 rows / 28,429.00, both succeeded. Item 5 not exercised (retention drops only partitions older than the data loaded). E7 pass (`ONLY_CLUSTER=rtu-cluster-a testdata.sh upload` after the rate removals and the deletion of cluster B): 2 new manifests processed; both months rebuilt (October 12,028 rows / 28,444.83, November 1,552 / 3,405.09; nise generates new usage); 0 rows of the 6 removed rates, 0 rows pointing to a deleted rate, 0 rows of deleted cluster B, 0 task errors on the priority, cost-model and summary workers |

E6 on `ephemeral-wufsxu` (`testdata.sh e6`, October recalculation of cluster B, rate removed DELAY seconds later): two attempts, both runs succeeded with 0 orphan rows and no `IntegrityError`, but neither hit the race window: with DELAY=5 the monthly insert (09:09:17.1) came before the removal and the cleanup deleted its rows (2,450); with DELAY=0.3 the run loaded the rates after the removal ("removing monthly cost [OCP_VM]"). The window between `_load_rates()` and the monthly insert is about 1 s; hitting it end to end needs an injected delay (like the "Path B" of the COST-81xx tickets). I2 is covered deterministically by `test_insert_with_deleted_rate_id_succeeds`. E7 ran on `pr-6425-2fde03a` (see Results).

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
