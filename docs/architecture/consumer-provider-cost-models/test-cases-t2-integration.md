# Test Case Specifications — Tier 2: Integration Tests

**IEEE 829-2008 Test Case Specification**

| Field | Value |
|-------|-------|
| Parent Plan | [test-plan.md](./test-plan.md) (COST-3920-TP-001) |
| Tier | T2 — Integration |
| Base Class | `MasuTestCase` |
| Coverage Target | ≥80% |
| Test Count | 34 |

---

## Module: `cost_models/test/test_context_migration.py`

### Class: `CostModelContextMigrationTest`

---

### TC-30: Forward migration creates default context per tenant

| Field | Value |
|-------|-------|
| Identifier | TC-30 |
| Test Items | Migration M4 `RunPython` — default context creation (C14) |
| BAC | BAC-9 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | None |

**Scenario**: Forward data migration creates the default "Consumer" context.

**Given**
- Schema is at `MIGRATE_FROM` state (`cost_models 0011`)
- One `CostModel` row exists in the tenant schema:
  ```python
  CostModel.objects.create(name="TC-30 Model", description="Test",
                           source_type="OCP", rates=[{...}])
  ```

**When**
- Forward migration is run to `MIGRATE_TO_DATA` (`cost_models 0015`)

**Then**
- A `CostModelContext` with `is_default=True` exists
- `default_ctx.name == "default"`
- `default_ctx.display_name == "Consumer"`
- `default_ctx.position == 1`

---

### TC-31: Forward migration assigns existing CostModelMap rows to default

| Field | Value |
|-------|-------|
| Identifier | TC-31 |
| Test Items | Migration M4 `RunPython` — CostModelMap backfill (C14) |
| BAC | BAC-10 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | TC-30 |
| Special Requirements | Uses raw SQL INSERT + `SET CONSTRAINTS ALL IMMEDIATE` to avoid pending trigger events |

**Scenario**: Existing CostModelMap rows get assigned to the default context.

**Given**
- Schema is at `MIGRATE_FROM` state
- A `CostModel` and `CostModelMap` row exist (created via raw SQL INSERT to avoid trigger issues):
  ```sql
  INSERT INTO cost_model (...) VALUES (...) RETURNING uuid;
  INSERT INTO cost_model_map (id, cost_model_id, provider_uuid) VALUES (DEFAULT, %s, %s);
  SET CONSTRAINTS ALL IMMEDIATE;
  ```

**When**
- Forward migration is run to `MIGRATE_TO_DATA`

**Then**
- `CostModelMap.objects.get(provider_uuid=uuid).cost_model_context` is not `None`
- The assigned context has `is_default == True`
- The assigned context has `name == "default"`

---

### TC-32: New unique constraint is active post-migration

| Field | Value |
|-------|-------|
| Identifier | TC-32 |
| Test Items | Migration M3 `AlterUniqueTogether` — new `(provider_uuid, cost_model_context)` constraint (C14) |
| BAC | BAC-6 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | TC-30 |

**Scenario**: After migration, duplicate (provider_uuid, context) is rejected.

**Given**
- Schema is at `MIGRATE_TO_DATA` with default context present
- A `CostModelMap` row exists for `(provider_uuid, default_context)`

**When**
- Inside `transaction.atomic()`:
  Create a second `CostModelMap` with the same `(provider_uuid, default_context)` but a different cost model

**Then**
- `IntegrityError` is raised — the new unique constraint is enforced

---

### TC-33: Old unique constraint is dropped post-migration

| Field | Value |
|-------|-------|
| Identifier | TC-33 |
| Test Items | Migration M3 — old `(provider_uuid, cost_model)` constraint removal (C14) |
| BAC | BAC-5 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | TC-30 |

**Scenario**: Same provider + same cost model with different contexts is now allowed.

**Given**
- Schema is at `MIGRATE_TO_DATA`
- Two contexts exist: `ctx_default` (default) and `ctx_provider` (created in test)

**When**
- Create two `CostModelMap` rows for the same `(provider_uuid, cost_model)` but with different contexts

**Then**
- Both rows persist without error
- `CostModelMap.objects.filter(provider_uuid=uuid).count() == 2`

---

### TC-34: Reverse migration removes context cleanly

| Field | Value |
|-------|-------|
| Identifier | TC-34 |
| Test Items | Migration M1–M4 reverse path (C14) |
| BAC | BAC-9 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | TC-30, TC-31 |
| Special Requirements | `information_schema` queries include `AND table_schema = current_schema()` |

**Scenario**: Reverse migration drops context column, table, and preserves CostModelMap rows.

**Given**
- Schema is at `MIGRATE_TO_DATA` with contexts and CostModelMap rows (created via raw SQL)

**When**
- Reverse migration is run back to `MIGRATE_FROM`

**Then**
- `cost_model_context_id` column no longer exists on `cost_model_map` table
  (verified via `information_schema.columns` with `table_schema = current_schema()`)
- `cost_model_context` table no longer exists
  (verified via `information_schema.tables` with `table_schema = current_schema()`)
- `CostModelMap` row survives the reverse migration (data not lost):
  `SELECT COUNT(*) FROM cost_model_map WHERE provider_uuid = %s` returns 1

---

### TC-35: Partial unique index blocks second default after migration

| Field | Value |
|-------|-------|
| Identifier | TC-35 |
| Test Items | Migration M1 — partial unique index on `is_default` (C14) |
| BAC | BAC-3 |
| Module | `cost_models/test/test_context_migration.py` |
| Dependencies | TC-30 |

**Scenario**: DB rejects second is_default=TRUE row per schema after migration.

**Given**
- Schema is at `MIGRATE_TO_DATA`
- One `CostModelContext` with `is_default=True` already exists (created by M4)

**When**
- Inside `transaction.atomic()`:
  `CostModelContext.objects.create(name="bad_default", display_name="Bad Default", is_default=True, position=2)`

**Then**
- `IntegrityError` is raised — the partial unique index is enforced

---

## Module: `masu/test/database/test_context_sql.py`

### Class: `CostModelDBAccessorContextTest`

---

### TC-40: Accessor filters by explicit context

| Field | Value |
|-------|-------|
| Identifier | TC-40 |
| Test Items | `CostModelDBAccessor` (C7) — context parameter |
| BAC | BAC-14 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Accessor with explicit cost_model_context returns the correct cost model.

**Given**
- Context "default" exists with a cost model assigned via `CostModelMap`
- `baker.make("CostModelMap", provider_uuid=uuid, cost_model=cm, cost_model_context=ctx)`

**When**
- `CostModelDBAccessor(schema, uuid, cost_model_context="default")` is opened as context manager

**Then**
- `accessor.cost_model == cm` — the correct cost model is resolved

---

### TC-41: Accessor defaults to tenant's default context when None

| Field | Value |
|-------|-------|
| Identifier | TC-41 |
| Test Items | `CostModelDBAccessor` (C7) — fallback behavior |
| BAC | BAC-15 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Accessor without explicit context falls back to the default context.

**Given**
- Context "default" (is_default=True) exists with a cost model assigned

**When**
- `CostModelDBAccessor(schema, uuid)` is opened (no `cost_model_context` argument)

**Then**
- `accessor.cost_model == cm` — falls back to the default context's cost model

---

### TC-42: Accessor returns None for unassigned context

| Field | Value |
|-------|-------|
| Identifier | TC-42 |
| Test Items | `CostModelDBAccessor` (C7) — missing context |
| BAC | BAC-14 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Requesting a context that has no cost model assigned returns None.

**Given**
- Two contexts exist: "default" (with cost model) and "provider" (no cost model)
- Cost model is only assigned to `ctx_consumer` via CostModelMap

**When**
- `CostModelDBAccessor(schema, uuid, cost_model_context="provider")` is opened

**Then**
- `accessor.cost_model is None` — no model exists for the requested context

---

### Class: `UsageCostsSQLContextTest`

---

### TC-43: Usage costs DELETE scoped by context

| Field | Value |
|-------|-------|
| Identifier | TC-43 |
| Test Items | `usage_costs.sql` — DELETE section (SQL) |
| BAC | BAC-17 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: The DELETE section of usage_costs.sql references cost_model_context.

**Given**
- The SQL file `sql/openshift/cost_model/usage_costs.sql` is loaded into memory

**When**
- The file content is split at the first `INSERT` keyword
- The portion before `INSERT` (the DELETE section) is inspected

**Then**
- The string `"cost_model_context"` is present in the DELETE section

---

### TC-44: Usage costs INSERT includes context column

| Field | Value |
|-------|-------|
| Identifier | TC-44 |
| Test Items | `usage_costs.sql` — INSERT section (SQL) |
| BAC | BAC-18 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: The INSERT section of usage_costs.sql includes cost_model_context.

**Given**
- The SQL file `usage_costs.sql` is loaded into memory

**When**
- The portion after the first `INSERT` keyword is inspected

**Then**
- The string `"cost_model_context"` is present in the INSERT section

---

### TC-45: Cross-context isolation via SQL template marker

| Field | Value |
|-------|-------|
| Identifier | TC-45 |
| Test Items | `usage_costs.sql` — Jinja template marker (SQL) |
| BAC | BAC-17 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: SQL contains the exact Jinja template marker for context scoping.

**Given**
- The SQL file `usage_costs.sql` is loaded

**When**
- The full SQL content is searched for the exact string

**Then**
- `"cost_model_context = {{cost_model_context}}"` is found in the SQL

---

### TC-49: Distribution SQL scoped by context

| Field | Value |
|-------|-------|
| Identifier | TC-49 |
| Test Items | `distribute_platform_cost.sql` (SQL) |
| BAC | BAC-19 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Platform distribution SQL includes cost_model_context.

**Given**
- The SQL file `cost_model/distribute_cost/distribute_platform_cost.sql` is loaded

**When**
- The full SQL content is inspected

**Then**
- The string `"cost_model_context"` is present

---

### TC-50: Cloud model rows unaffected (no context field)

| Field | Value |
|-------|-------|
| Identifier | TC-50 |
| Test Items | `AWSCostEntryLineItemDailySummary` model — no context field (SQL) |
| BAC | BAC-24 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: AWS (cloud) model does not have cost_model_context attribute.

**Given**
- The `AWSCostEntryLineItemDailySummary` model class is imported

**When**
- `hasattr(AWSCostEntryLineItemDailySummary, "cost_model_context")` is evaluated

**Then**
- Returns `False` — cloud models are not context-scoped

---

### Class: `CacheKeyContextTest`

---

### TC-51: Cache key includes context string

| Field | Value |
|-------|-------|
| Identifier | TC-51 |
| Test Items | `create_single_task_cache_key` (C9) |
| BAC | BAC-23 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Celery cache key contains the context name.

**Given**
- Cache key args include `"default"` as the context component:
  `["schema", "provider_uuid", "default", "2026-01-01", "2026-01-31"]`

**When**
- `create_single_task_cache_key("masu.processor.tasks.update_cost_model_costs", args)` is called

**Then**
- The returned key string contains `"default"` as a substring

---

### TC-52: Different contexts produce different cache keys

| Field | Value |
|-------|-------|
| Identifier | TC-52 |
| Test Items | `create_single_task_cache_key` (C9) |
| BAC | BAC-23 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | TC-51 |

**Scenario**: Cache keys for different contexts are distinct (no dedup collision).

**Given**
- Two sets of cache key args, identical except for context:
  - args_consumer: `[..., "default", ...]`
  - args_provider: `[..., "provider", ...]`

**When**
- Both keys are generated via `create_single_task_cache_key`

**Then**
- `key_consumer != key_provider` — distinct keys prevent dedup collision

---

### Class: `SelfHostedTrinoSQLContextTest`

---

### TC-53: All self-hosted SQL files include context param

| Field | Value |
|-------|-------|
| Identifier | TC-53 |
| Test Items | Self-hosted SQL templates (SQL) |
| BAC | BAC-20 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Every .sql file under self-hosted cost_model path references cost_model_context.

**Given**
- The directory `self_hosted_sql/openshift/cost_model/` is walked recursively

**When**
- Each `.sql` file is read and inspected

**Then**
- Every file contains `"cost_model_context"` (assertion per file)

---

### TC-54: All Trino SQL files include context param

| Field | Value |
|-------|-------|
| Identifier | TC-54 |
| Test Items | Trino SQL templates (SQL) |
| BAC | BAC-21 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Every .sql file under Trino cost_model path references cost_model_context.

**Given**
- The directory `trino_sql/openshift/cost_model/` is walked recursively

**When**
- Each `.sql` file is read and inspected

**Then**
- Every file contains `"cost_model_context"` (assertion per file)

---

### Class: `InlineSQLContextTest`

---

### TC-55: Inline DELETE method handles context

| Field | Value |
|-------|-------|
| Identifier | TC-55 |
| Test Items | `OCPCostModelCostUpdater._delete_tag_usage_costs` (C8) |
| BAC | BAC-22 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Python source of _delete_tag_usage_costs references cost_model_context.

**Given**
- The method `OCPCostModelCostUpdater._delete_tag_usage_costs` exists

**When**
- `inspect.getsource(method)` is called

**Then**
- The returned source string contains `"cost_model_context"`

---

### TC-56: populate_usage_costs passes context in SQL params

| Field | Value |
|-------|-------|
| Identifier | TC-56 |
| Test Items | `OCPReportDBAccessor.populate_usage_costs` (C8) |
| BAC | BAC-22 |
| Module | `masu/test/database/test_context_sql.py` |
| Dependencies | None |

**Scenario**: Python source of populate_usage_costs includes cost_model_context in sql_params.

**Given**
- The method `OCPReportDBAccessor.populate_usage_costs` exists

**When**
- `inspect.getsource(method)` is called

**Then**
- The returned source string contains `"cost_model_context"`

---

## Module: `masu/test/database/test_context_ui_summary.py`

### Class: `ContextColumnMigrationTest`

---

### TC-60: Daily summary table gets context column

| Field | Value |
|-------|-------|
| Identifier | TC-60 |
| Test Items | Migration M7 AddField — daily summary (C15) |
| BAC | BAC-11 |
| Module | `masu/test/database/test_context_ui_summary.py` |
| Dependencies | None |

**Scenario**: Migration adds cost_model_context column to daily summary.

**Given**
- Schema is at `MIGRATE_FROM` state (`reporting 0344`)

**When**
- Migration is run forward to `MIGRATE_TO` (`reporting 0346`)

**Then**
- `information_schema.columns` query (with `table_schema = current_schema()`) confirms
  `cost_model_context` column exists on `reporting_ocpusagelineitem_daily_summary`

---

### TC-61: All 13 UI summary tables get context column

| Field | Value |
|-------|-------|
| Identifier | TC-61 |
| Test Items | Migration M8 AddField — 13 UI summary tables (C15) |
| BAC | BAC-12 |
| Module | `masu/test/database/test_context_ui_summary.py` |
| Dependencies | TC-60 |

**Scenario**: Migration adds cost_model_context to all 13 UI summary tables.

**Given**
- Schema is at `MIGRATE_FROM` state

**When**
- Migration is run forward to `MIGRATE_TO`

**Then**
- For each of the 13 tables (verified via `subTest`):
  - `reporting_ocp_cost_summary_p`
  - `reporting_ocp_cost_summary_by_node_p`
  - `reporting_ocp_cost_summary_by_project_p`
  - `reporting_ocp_gpu_summary_p`
  - `reporting_ocp_network_summary_p`
  - `reporting_ocp_network_summary_by_node_p`
  - `reporting_ocp_network_summary_by_project_p`
  - `reporting_ocp_pod_summary_p`
  - `reporting_ocp_pod_summary_by_node_p`
  - `reporting_ocp_pod_summary_by_project_p`
  - `reporting_ocp_vm_summary_p`
  - `reporting_ocp_volume_summary_p`
  - `reporting_ocp_volume_summary_by_project_p`
- `cost_model_context` column exists (confirmed via `information_schema`)

---

### TC-62: Reverse migration removes context column

| Field | Value |
|-------|-------|
| Identifier | TC-62 |
| Test Items | Migration M7 reverse — daily summary (C15) |
| BAC | BAC-11 |
| Module | `masu/test/database/test_context_ui_summary.py` |
| Dependencies | TC-60 |

**Scenario**: Reverse migration removes cost_model_context from daily summary.

**Given**
- Schema is at `MIGRATE_TO` — context column is present
- Verified: `_column_exists("reporting_ocpusagelineitem_daily_summary", "cost_model_context")` returns `True`

**When**
- Reverse migration is run back to `MIGRATE_FROM`

**Then**
- `_column_exists("reporting_ocpusagelineitem_daily_summary", "cost_model_context")` returns `False`

---

## Module: `masu/test/processor/ocp/test_context_pipeline.py`

### Class: `MultiContextPipelineTest`

---

### TC-70: Pipeline dispatches once per context

| Field | Value |
|-------|-------|
| Identifier | TC-70 |
| Test Items | `update_cost_model_costs` task (C9) — multi-context dispatch |
| BAC | BAC-16 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Dependencies | None |

**Scenario**: Pipeline runs at least once per context for a provider.

**Given**
- Two contexts exist: "default" (consumer, position=1) and "provider" (position=2)
- `CostModelCostUpdater` is mocked

**When**
- `update_cost_model_costs(schema, provider_uuid, start, end, synchronous=True)` is called
  with no explicit `cost_model_context`

**Then**
- `mock_updater.update_cost_model_costs.call_count >= 2`
- The pipeline dispatched once per context

---

### TC-71: Accessor resolves correct rates per context

| Field | Value |
|-------|-------|
| Identifier | TC-71 |
| Test Items | `CostModelDBAccessor` (C7) — context-specific resolution |
| BAC | BAC-14 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Dependencies | None |

**Scenario**: Each context invocation resolves its own cost model's rates.

**Given**
- Context "default" with cost model `cm_consumer` (CPU rate: $10/core-hour)
- `CostModelMap` links `ocp_provider_uuid` to `cm_consumer` via `ctx_consumer`

**When**
- `CostModelDBAccessor(schema, ocp_provider_uuid, cost_model_context="default")` is opened

**Then**
- `accessor.cost_model == cm_consumer`

---

### TC-72: Pipeline step order (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-72 |
| BAC | BAC-17 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — behavioral coverage deferred to E2E TC-91 |

**Scenario**: Pipeline step-order behavior is deferred to E2E coverage.

**Given**
- Placeholder assertion in integration suite (`assert True`)

**When**
- `MultiContextPipelineTest.test_tc72_pipeline_step_order_placeholder` is executed

**Then**
- The test passes as a documented placeholder
- Behavioral assurance comes from E2E TC-91

---

### TC-73: Empty context zero cost (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-73 |
| BAC | BAC-32 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — behavioral coverage deferred to E2E TC-93 |

**Scenario**: Empty-context zero-cost behavior is deferred to E2E coverage.

**Given**
- Placeholder assertion in integration suite (`assert True`)

**When**
- `MultiContextPipelineTest.test_tc73_empty_context_zero_cost_placeholder` is executed

**Then**
- The test passes as a documented placeholder
- Behavioral assurance comes from E2E TC-93

---

### TC-74: Empty context preserves usage (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-74 |
| BAC | BAC-32 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — behavioral coverage deferred to E2E TC-93 |

**Scenario**: Empty-context usage-preservation behavior is deferred to E2E coverage.

**Given**
- Placeholder assertion in integration suite (`assert True`)

**When**
- `MultiContextPipelineTest.test_tc74_empty_context_preserves_usage_placeholder` is executed

**Then**
- The test passes as a documented placeholder
- Behavioral assurance comes from E2E TC-93

---

### TC-75: Sequential runs no corruption (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-75 |
| BAC | BAC-17 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — behavioral coverage deferred to E2E TC-91 and TC-98 |

**Scenario**: Sequential-run consistency behavior is deferred to E2E coverage.

**Given**
- Placeholder assertion in integration suite (`assert True`)

**When**
- `MultiContextPipelineTest.test_tc75_sequential_runs_no_corruption_placeholder` is executed

**Then**
- The test passes as a documented placeholder
- Behavioral assurance comes from E2E TC-91 and TC-98

---

### TC-76: Cloud infra in all contexts (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-76 |
| BAC | BAC-24 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — behavioral coverage deferred to E2E TC-99 |

**Scenario**: Cloud-infrastructure context neutrality is deferred to E2E coverage.

**Given**
- Placeholder assertion in integration suite (`assert True`)

**When**
- `MultiContextPipelineTest.test_tc76_cloud_infra_all_contexts_placeholder` is executed

**Then**
- The test passes as a documented placeholder
- Behavioral assurance comes from E2E TC-99

See [Deliberate Deviations](./test-plan.md#11-deliberate-deviations-from-spec) in the
test plan.

---

### Class: `AuditTriggerContextTest`

---

### TC-57: Audit trigger captures context (placeholder)

| Field | Value |
|-------|-------|
| Identifier | TC-57 |
| Test Items | Audit trigger — M5 (C14) |
| BAC | BAC-31 |
| Module | `masu/test/processor/ocp/test_context_pipeline.py` |
| Status | **Placeholder** — M5 audit trigger migration not yet implemented |

---

## Module: `cost_models/test/test_context_write_freeze.py`

### Class: `PipelineWriteFreezeTest`

---

### TC-WF5: Pipeline skips context-tagged writes when freeze active

| Field | Value |
|-------|-------|
| Identifier | TC-WF5 |
| Test Items | `update_cost_model_costs` task guard (C9, C13) |
| BAC | BAC-37 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: Pipeline returns early without running updater when freeze flag is on.

**Given**
- `is_context_writes_disabled` patched at `masu.processor.tasks.is_context_writes_disabled` to return `True`
- `CostModelCostUpdater` and `WorkerCache` mocked

**When**
- `update_cost_model_costs(schema, "test-provider-uuid", start_date="2026-01-01", end_date="2026-01-31", synchronous=True, cost_model_context="consumer")` is called

**Then**
- `CostModelCostUpdater` is never instantiated (`mock_updater.assert_not_called()`)
- The pipeline returned early due to the freeze guard

---

### TC-WF6: Pipeline runs normally when freeze off

| Field | Value |
|-------|-------|
| Identifier | TC-WF6 |
| Test Items | `update_cost_model_costs` task guard (C9, C13) |
| BAC | BAC-37 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: Pipeline executes updater when freeze flag is disabled.

**Given**
- `is_context_writes_disabled` patched to return `False`
- `CostModelCostUpdater`, `WorkerCache`, and `Provider` mocked

**When**
- `update_cost_model_costs(schema, "test-provider-uuid", ..., cost_model_context="consumer")` is called

**Then**
- `CostModelCostUpdater` is called exactly once (`mock_updater.assert_called_once()`)

---

### TC-WF7: Legacy path (None context) does not trigger freeze guard

| Field | Value |
|-------|-------|
| Identifier | TC-WF7 |
| Test Items | `update_cost_model_costs` task — None context path (C9, C13) |
| BAC | BAC-38 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: Pipeline runs for None context without checking freeze flag.

**Given**
- All `CostModelContext` objects deleted (no default context in DB)
- `is_context_writes_disabled` patched as a mock (call tracking enabled)
- `CostModelCostUpdater`, `WorkerCache`, and `Provider` mocked

**When**
- `update_cost_model_costs(schema, "test-provider-uuid", ..., cost_model_context=None)` is called

**Then**
- `is_context_writes_disabled` is never called (`mock_flag.assert_not_called()`)
- `CostModelCostUpdater` is called exactly once — the legacy path proceeds
