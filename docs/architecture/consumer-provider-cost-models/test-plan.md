# Test Plan — COST-3920 Consumer-Provider Cost Models

**IEEE 829-2008 Software Test Plan**

| Field | Value |
|-------|-------|
| Test Plan Identifier | COST-3920-TP-001 |
| Version | 3.1 |
| Date | 2026-04-09 |
| Author | COST-3920 Engineering |
| Status | Design Proposal |
| Parent Feature | COST-3920: Consumer-Provider Cost Models |
| Spec References | [phased-delivery.md](./phased-delivery.md), [prd-gap-analysis.md](./prd-gap-analysis.md), [risk-register.md](./risk-register.md) |

---

## 1. Introduction

### 1.1 Purpose

This test plan defines the verification and validation strategy for
COST-3920 (Consumer-Provider Cost Models). It covers all phases of
the feature with behavioral acceptance criteria, following koku
testing conventions. Each test case is specified as a BDD scenario
(Given/When/Then) derived from the proposed test implementation.

### 1.2 Scope

**In scope:**
- Context entity CRUD (model, serializer, viewset)
- Assignment with context (CostModelMap, CostModelManager)
- Schema migrations (forward/reverse, data migration, backfill)
- Per-context pipeline execution (accessor, updater, SQL templates)
- API integration (query parameter, response filtering)
- RBAC (Koku-side authorization, context permission)
- Write-freeze guards (Unleash flag, serializer, pipeline)
- Cross-context data isolation

**Out of scope:**
- Frontend UI changes (context dropdown, notifications)
- Kessel/ReBAC integration (deferred to v2)
- `ocp_tag_mapping_update_daily_summary.sql` context scoping
- OCP-on-cloud cross-provider context interaction

### 1.3 Definitions

| Term | Definition |
|------|-----------|
| **Context** | A `CostModelContext` instance (e.g., "Consumer", "Provider") |
| **BAC** | Business Acceptance Criterion |
| **TC** | Test Case |
| **TDD** | Test-Driven Development (Red/Green/Refactor) |
| **SUT** | System Under Test |

---

## 2. Test Items

### 2.1 Components Under Test

| ID | Component | File | Type |
|----|-----------|------|------|
| C1 | `CostModelContext` model | `cost_models/models.py` | **NEW** |
| C2 | `CostModelMap` + `cost_model_context` FK | `cost_models/models.py` | **MODIFIED** |
| C3 | `CostModelManager.update_provider_uuids` | `cost_models/cost_model_manager.py` | **MODIFIED** |
| C4 | `CostModelContextSerializer` | `cost_models/serializers.py` | **NEW** |
| C5 | `CostModelSerializer` (context field) | `cost_models/serializers.py` | **MODIFIED** |
| C6 | `CostModelContextViewSet` | `cost_models/views.py` | **NEW** |
| C7 | `CostModelDBAccessor` (context parameter) | `masu/database/cost_model_db_accessor.py` | **MODIFIED** |
| C8 | `OCPCostModelCostUpdater` (context threading) | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | **MODIFIED** |
| C9 | `update_cost_model_costs` task (context dispatch) | `masu/processor/tasks.py` | **MODIFIED** |
| C10 | `OCPQueryParamSerializer` (context field) | `api/report/ocp/serializers.py` | **MODIFIED** |
| C11 | `OCPReportQueryHandler` (context filtering) | `api/report/ocp/query_handler.py` | **MODIFIED** |
| C12 | `CostModelContextPermission` | `api/common/permissions/cost_model_context_access.py` | **NEW** |
| C13 | `is_context_writes_disabled()` | `masu/processor/__init__.py` | **NEW** |
| C14 | Migrations M1–M6 (cost_models) | `cost_models/migrations/` | **NEW** |
| C15 | Migrations M7–M10 (reporting) | `reporting/migrations/` | **NEW** |

### 2.2 SQL Artifacts Under Test (49 files)

| Category | Count | Path |
|----------|-------|------|
| Standard cost model SQL | 16 | `masu/database/sql/openshift/cost_model/` |
| Self-hosted cost model SQL | 9 | `masu/database/self_hosted_sql/openshift/cost_model/` |
| Trino cost model SQL | 9 | `masu/database/trino_sql/openshift/cost_model/` |
| Standard UI summary SQL | 13 | `masu/database/sql/openshift/ui_summary/` |
| UI summary variants | 2 | self-hosted + Trino usage-only |

### 2.3 Features NOT Tested

- `ocp_tag_mapping_update_daily_summary.sql` — out of scope
- Frontend context dropdown — not in koku
- Kessel/ReBAC — deferred to v2
- Trino live execution — mocked in tests (no local Trino server)

---

## 3. Features to Be Tested

### 3.1 Business Acceptance Criteria (38 BACs)

#### Phase 1 — Context Entity + Schema (10 BACs)

| BAC | Description | Priority | Components |
|-----|-------------|----------|------------|
| BAC-1 | `CostModelContext.objects.create()` succeeds with valid name/display_name | P1 | C1 |
| BAC-2 | Max 3 contexts per tenant enforced (DB CHECK + serializer) | P1 | C1, C4 |
| BAC-3 | Exactly one default context per tenant (partial unique index) | P1 | C1 |
| BAC-4 | Default context cannot be deleted | P1 | C1, C4, C6 |
| BAC-5 | `CostModelMap` accepts multiple rows for same provider with different contexts | P1 | C2 |
| BAC-6 | `CostModelMap` rejects duplicate `(provider_uuid, cost_model_context)` | P1 | C2 |
| BAC-7 | `update_provider_uuids` allows same provider in different contexts | P1 | C3 |
| BAC-8 | `update_provider_uuids` rejects same provider+context twice | P1 | C3 |
| BAC-9 | Data migration creates default context per tenant schema | P1 | C14 |
| BAC-10 | Data migration assigns existing `CostModelMap` rows to default context | P1 | C14 |

#### Phase 2 — Reporting Schema + Backfill (3 BACs)

| BAC | Description | Priority | Components |
|-----|-------------|----------|------------|
| BAC-11 | `cost_model_context` column added to daily summary table | P1 | C15 |
| BAC-12 | `cost_model_context` column added to all 13 UI summary tables | P1 | C15 |
| BAC-13 | Backfill sets `cost_model_context = 'default'` where `cost_model_rate_type IS NOT NULL` | P1 | C15 |

#### Phase 3 — Pipeline + SQL (12 BACs)

| BAC | Description | Priority | Components |
|-----|-------------|----------|------------|
| BAC-14 | `CostModelDBAccessor(context=X)` returns correct cost model | P1 | C7 |
| BAC-15 | `CostModelDBAccessor(context=None)` falls back to default | P1 | C7 |
| BAC-16 | Pipeline executes per-context with context-specific rates | P1 | C8, C9 |
| BAC-17 | SQL DELETE scopes by `cost_model_context` — no cross-context deletion | P1 | SQL |
| BAC-18 | SQL INSERT includes `cost_model_context` in output rows | P1 | SQL |
| BAC-19 | Distribution SQL scopes by `cost_model_context` | P1 | SQL |
| BAC-20 | Self-hosted SQL variants include `cost_model_context` | P2 | SQL |
| BAC-21 | Trino SQL variants include `cost_model_context` | P2 | SQL |
| BAC-22 | Python inline SQL handles `cost_model_context` | P2 | C8 |
| BAC-23 | Celery cache key includes context (no dedup collision) | P1 | C9 |
| BAC-24 | Cloud rows (`cost_model_rate_type = NULL`) unaffected | P1 | SQL |
| BAC-25 | UI summary GROUP BY includes `cost_model_context` | P1 | SQL |

#### Phase 4 — API + RBAC (8 BACs)

| BAC | Description | Priority | Components |
|-----|-------------|----------|------------|
| BAC-26 | `cost_model_context` query parameter accepted on OCP report endpoints | P1 | C10, C11 |
| BAC-27 | Report response filters cost data by requested context | P1 | C11 |
| BAC-28 | `CostModelContextPermission` allows admin bypass | P1 | C12 |
| BAC-29 | `CostModelContextPermission` denies unpermitted users | P1 | C12 |
| BAC-30 | Context CRUD API lifecycle (POST/GET/PUT/DELETE) | P1 | C4, C6 |
| BAC-31 | Audit trigger captures context array | P2 | C14 |
| BAC-32 | Empty context (no cost model) shows $0 cost | P2 | C7, C11 |
| BAC-33 | Report views pass through when `cost_model_context` absent (backward-compat) | P1 | C12 |

#### Phase 5 — Write-Freeze + Data Consistency (5 BACs)

| BAC | Description | Priority | Components |
|-----|-------------|----------|------------|
| BAC-34 | Context creation blocked when write-freeze active | P1 | C4, C13 |
| BAC-35 | Context update blocked when write-freeze active | P1 | C4, C13 |
| BAC-36 | Context read/list allowed during write-freeze | P1 | C6, C13 |
| BAC-37 | Pipeline skips context-tagged writes when freeze active | P1 | C9, C13 |
| BAC-38 | Pipeline runs for `None` context without triggering freeze guard | P1 | C9, C13 |

---

## 4. Approach

### 4.1 Test Tiers

| Tier | Description | Base Class | Coverage Target | Mocking Strategy |
|------|-------------|------------|-----------------|------------------|
| **T1: Unit** | Model validation, serializer logic, permission checks, manager guards | `IamTestCase` | ≥85% | Mock at ORM/accessor boundary where needed |
| **T2: Integration** | SQL execution, accessor methods, migration forward/reverse, DB constraints | `MasuTestCase` | ≥80% | Real DB; mock Trino connections |
| **T3: E2E** | Full pipeline orchestration, API request/response, cross-context isolation | `MasuTestCase` | ≥80% | Real DB + pipeline; mock Trino |

### 4.2 Anti-Pattern Avoidance

| Anti-Pattern | Mitigation |
|--------------|------------|
| **Over-mocking** | T2/T3 tests use real `CostModelDBAccessor` with seeded DB data |
| **Shared mutable state** | Each test opens its own accessor context manager; `setUp` clears contexts |
| **Brittle SQL assertions** | Assert param dicts and template markers, not raw SQL strings |
| **assertLogs misuse** | Always use `with self.assertLogs(...) as cm:` context manager |
| **Random test data** | Deterministic rate values ($10, $20, $50); reserve random for property-based |
| **Testing implementation** | Test via public API; private methods only where business logic requires |
| **model_bakery misuse** | Use `baker.make()` not `Model.objects.create()` except in migration tests |

### 4.3 TDD Methodology

Each implementation phase follows strict Red-Green-Refactor:

1. **TDD Red**: Write failing tests first. Tests define expected behavior from BAC.
2. **TDD Green**: Implement minimum code to make all Red tests pass.
3. **TDD Refactor**: Clean up. Remove duplication. Ensure conventions. No new behavior.

---

## 5. Test Cases (82 tests across 10 modules)

Each test case below is summarized in table form for quick reference.
Full IEEE 829 Test Case Specifications (with structured
Given/When/Then scenarios, test items, dependencies, and special
requirements) are in the per-tier companion documents:

- **[test-cases-t1-unit.md](./test-cases-t1-unit.md)** — 25 unit tests (model, serializer, permission, manager)
- **[test-cases-t2-integration.md](./test-cases-t2-integration.md)** — 34 integration tests (SQL, accessor, migration, DB constraints, pipeline)
- **[test-cases-t3-e2e.md](./test-cases-t3-e2e.md)** — 24 E2E tests (full pipeline, API, cross-context isolation, write-freeze)

### 5.1 Module: `cost_models/test/test_cost_model_context.py` (17 tests)

#### Class: `CostModelContextModelTest` — T1 Unit

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-01](./test-cases-t1-unit.md#tc-01-context-creation-with-valid-data) | BAC-1 | Tenant schema with no contexts | `baker.make("CostModelContext", name="provider", display_name="Provider", position=2, is_default=False)` | Context persists with correct `name`, `display_name`, `position`, `uuid`, `created_timestamp` |
| [TC-02](./test-cases-t1-unit.md#tc-02-max-3-contexts-enforced-by-db-check) | BAC-2 | 3 contexts already exist (positions 1-3) | `baker.make("CostModelContext", position=4)` inside `transaction.atomic()` | `IntegrityError` raised (DB CHECK constraint rejects position > 3) |
| [TC-03](./test-cases-t1-unit.md#tc-03-one-default-context-enforced-by-partial-unique-index) | BAC-3 | 1 context with `is_default=True` exists | `baker.make("CostModelContext", is_default=True)` inside `transaction.atomic()` | `IntegrityError` raised (partial unique index blocks 2nd default) |
| [TC-04a](./test-cases-t1-unit.md#tc-04a-valid-positions-1-2-3-accepted) | BAC-2 | Empty tenant schema | Create contexts with positions 1, 2, 3 sequentially | All 3 persist with correct positions |
| [TC-04b](./test-cases-t1-unit.md#tc-04b-invalid-positions-0-4--1-rejected) | BAC-2 | Empty tenant schema | Create context with position 0, 4, or -1 inside `transaction.atomic()` | `IntegrityError` for each invalid position |
| [TC-05a](./test-cases-t1-unit.md#tc-05a-default-context-deletion-is-blocked) | BAC-4 | Context with `is_default=True` exists | `default_ctx.delete()` | `ValidationError` or `IntegrityError` raised — deletion blocked |
| [TC-05b](./test-cases-t1-unit.md#tc-05b-non-default-context-deletion-is-allowed) | BAC-4 | Non-default context exists | `ctx.delete()` | Context deleted; `CostModelContext.objects.filter(uuid=ctx_uuid).exists()` returns `False` |

#### Class: `CostModelMapContextTest` — T1 Unit

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-09](./test-cases-t1-unit.md#tc-09-same-provider-with-different-contexts-allowed) | BAC-5 | Two contexts ("consumer", "provider") and one cost model | Create 2 `CostModelMap` rows for same `provider_uuid` with different contexts | Both rows persist; `CostModelMap.objects.filter(provider_uuid=uuid).count() == 2` |
| [TC-10](./test-cases-t1-unit.md#tc-10-duplicate-provider--context-rejected) | BAC-6 | One `CostModelMap` row exists for `(provider_uuid, context)` | Create second `CostModelMap` for same `(provider_uuid, context)` inside `transaction.atomic()` | `IntegrityError` raised (unique constraint) |

#### Class: `CostModelManagerContextTest` — T1 Unit

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-06](./test-cases-t1-unit.md#tc-06-manager-allows-same-provider-in-different-contexts) | BAC-7 | Two contexts exist; cost model 1 assigned to consumer | `CostModelManager(cm2).update_provider_uuids([uuid], cost_model_context=provider)` | Succeeds; 2 `CostModelMap` rows for same provider |
| [TC-07](./test-cases-t1-unit.md#tc-07-manager-rejects-same-provider--same-context) | BAC-8 | Context exists; cost model 1 already assigned to `(uuid, ctx)` | `CostModelManager(cm2).update_provider_uuids([uuid], cost_model_context=ctx)` | `CostModelException` raised with descriptive message |
| [TC-08](./test-cases-t1-unit.md#tc-08-manager-defaults-to-tenants-default-context-when-none) | BAC-7 | Default context exists; `cost_model_context` not passed | `CostModelManager(cm).update_provider_uuids([uuid])` | `CostModelMap.cost_model_context.name == "default"` — auto-resolved |

#### Class: `CostModelContextSerializerTest` — T1 Unit

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-11](./test-cases-t1-unit.md#tc-11-serializer-accepts-valid-context-data) | BAC-1 | Default context exists | `CostModelContextSerializer(data={"name": "provider", "display_name": "Provider"}).is_valid()` | Returns `True` |
| [TC-12](./test-cases-t1-unit.md#tc-12-serializer-rejects-4th-context) | BAC-2 | 3 contexts already exist | `CostModelContextSerializer(data={"name": "c4", "display_name": "C4"}).is_valid()` | Returns `False` — 4th rejected |
| [TC-13](./test-cases-t1-unit.md#tc-13-default-context-not-deletable-via-serializermodel-guard) | BAC-4 | Default context exists | `default_ctx.delete()` | `ValidationError` or `IntegrityError` raised |
| [TC-14](./test-cases-t1-unit.md#tc-14-costmodelserializer-accepts-context-uuid) | BAC-5 | Default context exists | `CostModelSerializer(data={..., "cost_model_context": str(ctx.uuid)}).is_valid()` | Returns `True` — context UUID accepted |
| [TC-15](./test-cases-t1-unit.md#tc-15-costmodelserializer-defaults-context-when-absent) | BAC-7 | Default context exists; no `cost_model_context` in data | `CostModelSerializer(data={..., no context field}).is_valid()` | Returns `True` — defaults to tenant's default context |
| [TC-XX](./test-cases-t1-unit.md#tc-xx-backward-compatible-cost-model-creation-without-context) | BAC-7 | Default context exists; no `cost_model_context` in data | `serializer.save()` | Instance created successfully — backward-compatible |

---

### 5.2 Module: `cost_models/test/test_cost_model_context_view.py` (1 test)

#### Class: `CostModelContextViewSetTest` — T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-85](./test-cases-t3-e2e.md#tc-85-context-crud-api-lifecycle) | BAC-30 | Default context exists; authenticated API client | POST `/cost-model-contexts/` → GET list → PUT detail → DELETE detail → GET detail | POST=201 (created); GET=200 (name in list); PUT=200 (display_name updated); DELETE=204; final GET=404 |

---

### 5.3 Module: `cost_models/test/test_context_migration.py` (6 tests)

#### Class: `CostModelContextMigrationTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-30](./test-cases-t2-integration.md#tc-30-forward-migration-creates-default-context-per-tenant) | BAC-9 | Schema at `MIGRATE_FROM` with one `CostModel` row | Run forward migration to `MIGRATE_TO_DATA` | `CostModelContext(is_default=True, name="default", display_name="Consumer", position=1)` exists |
| [TC-31](./test-cases-t2-integration.md#tc-31-forward-migration-assigns-existing-costmodelmap-rows-to-default) | BAC-10 | Schema at `MIGRATE_FROM` with `CostModelMap` row (raw SQL INSERT) | Run forward migration to `MIGRATE_TO_DATA` | `CostModelMap.cost_model_context` is set, `is_default=True`, `name="default"` |
| [TC-32](./test-cases-t2-integration.md#tc-32-new-unique-constraint-is-active-post-migration) | BAC-6 | Schema at `MIGRATE_TO_DATA` with default context | Create 2 `CostModelMap` rows for same `(provider_uuid, context)` | `IntegrityError` — new unique constraint active |
| [TC-33](./test-cases-t2-integration.md#tc-33-old-unique-constraint-is-dropped-post-migration) | BAC-5 | Schema at `MIGRATE_TO_DATA` with 2 contexts | Create 2 `CostModelMap` rows for same `(provider_uuid, cost_model)` but different contexts | Succeeds — old `(provider_uuid, cost_model)` constraint dropped |
| [TC-34](./test-cases-t2-integration.md#tc-34-reverse-migration-removes-context-cleanly) | BAC-9 | Schema at `MIGRATE_TO_DATA` with contexts and map rows | Reverse migration to `MIGRATE_FROM` | `cost_model_context_id` column dropped; `cost_model_context` table dropped; `CostModelMap` row survives |
| [TC-35](./test-cases-t2-integration.md#tc-35-partial-unique-index-blocks-second-default-after-migration) | BAC-3 | Schema at `MIGRATE_TO_DATA` with one default context | Create second context with `is_default=True` inside `transaction.atomic()` | `IntegrityError` — partial unique index active |

---

### 5.4 Module: `cost_models/test/test_context_write_freeze.py` (7 tests)

#### Class: `ContextWriteFreezeAPITest` — T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-WF1](./test-cases-t3-e2e.md#tc-wf1-context-creation-blocked-when-freeze-active) | BAC-34 | Default context exists; `is_context_writes_disabled` patched to return `True` | POST `/cost-model-contexts/` with `{"name": "provider", "display_name": "Provider"}` | HTTP 400; response body contains "frozen" |
| [TC-WF2](./test-cases-t3-e2e.md#tc-wf2-context-update-blocked-when-freeze-active) | BAC-35 | Default context exists; freeze flag active | PUT `/cost-model-contexts/{uuid}/` with updated display_name | HTTP 400; response body contains "frozen" |
| [TC-WF3](./test-cases-t3-e2e.md#tc-wf3-context-read-allowed-during-freeze) | BAC-36 | Default context exists; freeze flag active | GET `/cost-model-contexts/` | HTTP 200 — reads not blocked |
| [TC-WF4](./test-cases-t3-e2e.md#tc-wf4-context-creation-allowed-when-freeze-off) | BAC-34 | Default context exists; `is_context_writes_disabled` patched to return `False` | POST `/cost-model-contexts/` with `{"name": "provider", "display_name": "Provider"}` | HTTP 201 — creation proceeds |

#### Class: `PipelineWriteFreezeTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-WF5](./test-cases-t2-integration.md#tc-wf5-pipeline-skips-context-tagged-writes-when-freeze-active) | BAC-37 | Freeze flag active; `CostModelCostUpdater` and `WorkerCache` mocked | `update_cost_model_costs(..., cost_model_context="consumer", synchronous=True)` | `CostModelCostUpdater` never instantiated — pipeline returns early |
| [TC-WF6](./test-cases-t2-integration.md#tc-wf6-pipeline-runs-normally-when-freeze-off) | BAC-37 | Freeze flag disabled; `CostModelCostUpdater` and `Provider` mocked | `update_cost_model_costs(..., cost_model_context="consumer", synchronous=True)` | `CostModelCostUpdater` called once — pipeline executes |
| [TC-WF7](./test-cases-t2-integration.md#tc-wf7-legacy-path-none-context-does-not-trigger-freeze-guard) | BAC-38 | All `CostModelContext` objects deleted; freeze flag mock tracked | `update_cost_model_costs(..., cost_model_context=None, synchronous=True)` | `is_context_writes_disabled` never called; `CostModelCostUpdater` called once |

---

### 5.5 Module: `masu/test/processor/ocp/test_context_pipeline.py` (8 tests)

#### Class: `MultiContextPipelineTest` — T2 Integration / T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-70](./test-cases-t2-integration.md#tc-70-pipeline-dispatches-once-per-context) | BAC-16 | 2 contexts ("consumer", "provider"); `CostModelCostUpdater` mocked | `update_cost_model_costs(..., synchronous=True)` with no explicit context | `mock_updater.update_cost_model_costs.call_count >= 2` — dispatched per context |
| [TC-71](./test-cases-t2-integration.md#tc-71-accessor-resolves-correct-rates-per-context) | BAC-14 | Context "default" with cost model ($10 CPU rate); `CostModelMap` assigned | `CostModelDBAccessor(schema, uuid, cost_model_context="default")` | `accessor.cost_model == cm_consumer` — correct model resolved |
| [TC-72–76](./test-cases-t2-integration.md#tc-72-through-tc-76-placeholder-tests) | BAC-17,32,24 | — | — | Placeholders — covered by E2E TC-91, TC-93, TC-98, TC-99 |

#### Class: `AuditTriggerContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-57](./test-cases-t2-integration.md#tc-57-audit-trigger-captures-context-placeholder) | BAC-31 | — | — | Placeholder — M5 audit trigger not yet implemented |

---

### 5.6 Module: `masu/test/database/test_context_sql.py` (14 tests)

#### Class: `CostModelDBAccessorContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-40](./test-cases-t2-integration.md#tc-40-accessor-filters-by-explicit-context) | BAC-14 | Context "default" with cost model assigned via `CostModelMap` | `CostModelDBAccessor(schema, uuid, cost_model_context="default")` | `accessor.cost_model == cm` |
| [TC-41](./test-cases-t2-integration.md#tc-41-accessor-defaults-to-tenants-default-context-when-none) | BAC-15 | Context "default" with cost model assigned; no explicit context param | `CostModelDBAccessor(schema, uuid)` | `accessor.cost_model == cm` — falls back to default |
| [TC-42](./test-cases-t2-integration.md#tc-42-accessor-returns-none-for-unassigned-context) | BAC-14 | Cost model assigned to "consumer" context only | `CostModelDBAccessor(schema, uuid, cost_model_context="provider")` | `accessor.cost_model is None` — no model for requested context |

#### Class: `UsageCostsSQLContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-43](./test-cases-t2-integration.md#tc-43-usage-costs-delete-scoped-by-context) | BAC-17 | `usage_costs.sql` file loaded | Parse DELETE section (before first INSERT) | String `"cost_model_context"` present in DELETE section |
| [TC-44](./test-cases-t2-integration.md#tc-44-usage-costs-insert-includes-context-column) | BAC-18 | `usage_costs.sql` file loaded | Parse INSERT section (after first INSERT keyword) | String `"cost_model_context"` present in INSERT section |
| [TC-45](./test-cases-t2-integration.md#tc-45-cross-context-isolation-via-sql-template-marker) | BAC-17 | `usage_costs.sql` file loaded | Search for exact template marker | `"cost_model_context = {{cost_model_context}}"` found in SQL |
| [TC-49](./test-cases-t2-integration.md#tc-49-distribution-sql-scoped-by-context) | BAC-19 | `distribute_platform_cost.sql` loaded | Search for context reference | String `"cost_model_context"` present |
| [TC-50](./test-cases-t2-integration.md#tc-50-cloud-model-rows-unaffected-no-context-field) | BAC-24 | `AWSCostEntryLineItemDailySummary` model inspected | Check for attribute | `hasattr(model, "cost_model_context")` returns `False` — AWS model unaffected |

#### Class: `CacheKeyContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-51](./test-cases-t2-integration.md#tc-51-cache-key-includes-context-string) | BAC-23 | Cache key created with args including `"default"` context | `create_single_task_cache_key(task_name, [..., "default", ...])` | `"default"` substring present in returned key |
| [TC-52](./test-cases-t2-integration.md#tc-52-different-contexts-produce-different-cache-keys) | BAC-23 | Two cache keys with different context args ("default" vs "provider") | Compare both keys | Keys are not equal — different contexts produce different keys |

#### Class: `SelfHostedTrinoSQLContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-53](./test-cases-t2-integration.md#tc-53-all-self-hosted-sql-files-include-context-param) | BAC-20 | All `.sql` files under `self_hosted_sql/openshift/cost_model/` | Read each file | Every file contains `"cost_model_context"` |
| [TC-54](./test-cases-t2-integration.md#tc-54-all-trino-sql-files-include-context-param) | BAC-21 | All `.sql` files under `trino_sql/openshift/cost_model/` | Read each file | Every file contains `"cost_model_context"` |

#### Class: `InlineSQLContextTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-55](./test-cases-t2-integration.md#tc-55-inline-delete-method-handles-context) | BAC-22 | `OCPCostModelCostUpdater._delete_tag_usage_costs` source inspected | `inspect.getsource(method)` | Source contains `"cost_model_context"` |
| [TC-56](./test-cases-t2-integration.md#tc-56-populate_usage_costs-passes-context-in-sql-params) | BAC-22 | `OCPReportDBAccessor.populate_usage_costs` source inspected | `inspect.getsource(method)` | Source contains `"cost_model_context"` |

---

### 5.7 Module: `masu/test/database/test_context_ui_summary.py` (3 tests)

#### Class: `ContextColumnMigrationTest` — T2 Integration

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-60](./test-cases-t2-integration.md#tc-60-daily-summary-table-gets-context-column) | BAC-11 | Schema at `MIGRATE_FROM` | Run migration to `MIGRATE_TO` | `information_schema.columns` confirms `cost_model_context` on `reporting_ocpusagelineitem_daily_summary` |
| [TC-61](./test-cases-t2-integration.md#tc-61-all-13-ui-summary-tables-get-context-column) | BAC-12 | Schema at `MIGRATE_FROM` | Run migration to `MIGRATE_TO` | `cost_model_context` column exists on all 13 `reporting_ocp_*_summary_p` tables (verified with `subTest`) |
| [TC-62](./test-cases-t2-integration.md#tc-62-reverse-migration-removes-context-column) | BAC-11 | Schema at `MIGRATE_TO` with context column present | Reverse migration to `MIGRATE_FROM` | `cost_model_context` column no longer exists on daily summary table |

---

### 5.8 Module: `api/report/test/ocp/test_context_api.py` (7 tests)

#### Class: `OCPContextQueryParamSerializerTest` — T1 Unit / T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-22](./test-cases-t3-e2e.md#tc-22-cost_model_context-parameter-accepted) | BAC-26 | Authenticated client | GET `/reports/openshift/costs/?cost_model_context=consumer` | HTTP 200; `response.meta.cost_model_context == "consumer"` |
| [TC-23](./test-cases-t3-e2e.md#tc-23-missing-cost_model_context-has-no-context-in-meta) | BAC-33 | Authenticated client | GET `/reports/openshift/costs/` (no context param) | HTTP 200; `"cost_model_context" not in response.meta` — backward-compatible |

#### Class: `OCPContextReportAPITest` — T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-80](./test-cases-t3-e2e.md#tc-80-cost-endpoint-with-context-returns-200) | BAC-26 | Authenticated client | GET `/reports/openshift/costs/?cost_model_context=consumer` | HTTP 200 |
| [TC-81](./test-cases-t3-e2e.md#tc-81-response-filtered-by-context) | BAC-27 | Authenticated client | GET `/reports/openshift/costs/?cost_model_context=consumer` | `response.meta.cost_model_context == "consumer"` |
| [TC-82](./test-cases-t3-e2e.md#tc-82-missing-context-uses-default-no-regression) | BAC-33 | Authenticated client | GET `/reports/openshift/costs/` (no context param) | HTTP 200 — no regression |
| [TC-83](./test-cases-t3-e2e.md#tc-83-currency-annotation-context-aware) | BAC-27 | Authenticated client | GET `/reports/openshift/costs/?cost_model_context=consumer` | Response includes data (verify currency annotation is context-aware) |
| [TC-84](./test-cases-t3-e2e.md#tc-84-unpermittednonexistent-context-handled-gracefully) | BAC-29 | Authenticated client | GET `/reports/openshift/costs/?cost_model_context=nonexistent` | HTTP 200 or 400 — unpermitted/nonexistent context handled gracefully |

---

### 5.9 Module: `api/common/permissions/test/test_context_permission.py` (7 tests)

#### Class: `CostModelContextPermissionTest` — T1 Unit

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-16](./test-cases-t1-unit.md#tc-16-admin-user-bypasses-context-check) | BAC-28 | `ENHANCED_ORG_ADMIN=True`; admin user; `query_params={"cost_model_context": "provider"}` | `perm.has_permission(request, None)` | Returns `True` — admin bypass |
| [TC-17](./test-cases-t1-unit.md#tc-17-unpermitted-user-denied) | BAC-29 | User with `cost_model.read=[]` (empty); `query_params={"cost_model_context": "consumer"}` | `perm.has_permission(request, None)` | Returns `False` — denied |
| [TC-18](./test-cases-t1-unit.md#tc-18-permitted-user-allowed-no-context-param) | BAC-33 | User with `cost_model.read=["*"]`; `query_params={}` (no context param) | `perm.has_permission(request, None)` | Returns `True` — pass-through when no context requested |
| [TC-19a](./test-cases-t1-unit.md#tc-19a-missing-customer-attribute-returns-false) | BAC-29 | User with `access=None`, `customer=None`; `query_params={"cost_model_context": "consumer"}` | `perm.has_permission(request, None)` | Returns `False` |
| [TC-19b](./test-cases-t1-unit.md#tc-19b-no-context-param-allows-access-regardless) | BAC-33 | User with `access=None`; `query_params={}` (no context param) | `perm.has_permission(request, None)` | Returns `True` — pass-through |
| [TC-20](./test-cases-t1-unit.md#tc-20-empty-access-dict-returns-false) | BAC-29 | User with `access={}` (empty dict); `query_params={"cost_model_context": "consumer"}` | `perm.has_permission(request, None)` | Returns `False` |
| [TC-21](./test-cases-t1-unit.md#tc-21-missing-cost_model-key-does-not-raise-keyerror) | BAC-29 | User with `access={"aws.account": {"read": ["*"]}}` (no `cost_model` key); context requested | `perm.has_permission(request, None)` | Returns `False` — no `KeyError` raised |

---

### 5.10 Module: `cost_models/test/test_context_e2e.py` (12 tests)

#### Class: `PipelineSmokeE2ETest` — T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-90](./test-cases-t3-e2e.md#tc-90-single-context-pipeline-smoke-test) | BAC-16, BAC-27 | Context "default" with cost model ($10/core-hour CPU, Infrastructure); `CostModelMap` assigned; Trino mocked | Run pipeline for `cost_model_context="default"`; then GET `/reports/openshift/costs/?cost_model_context=default` | DB: `OCPUsageLineItemDailySummary` rows with `cost_model_context="default"` and `cost_model_rate_type="Infrastructure"` exist; `sum(cost_model_cpu_cost) > 0`. API: `response.meta.cost_model_context == "default"` |
| [TC-91](./test-cases-t3-e2e.md#tc-91-dual-context-isolation-smoke-test) | BAC-16, BAC-17 | Two contexts: consumer ($10), provider ($20); both assigned to same cluster; Trino mocked | Run pipeline for "consumer" then "provider" | DB: `provider_cost / consumer_cost ≈ 2.0 (±0.1)`. API: each context returns its own `cost_model_context` in meta. Cross-context isolation verified |

#### Class: `APIContextE2ETest` — T3 E2E

| TC | BAC | Given | When | Then |
|----|-----|-------|------|------|
| [TC-92](./test-cases-t3-e2e.md#tc-92-explicit-default-equals-implicit-backward-compat) | BAC-33, BAC-27 | Default context with rate; pipeline run for "default" | GET with `?cost_model_context=default` vs GET without param | Explicit: `meta.cost_model_context == "default"`. Implicit: `"cost_model_context" not in meta` |
| [TC-93](./test-cases-t3-e2e.md#tc-93-empty-context-shows-0-cost) | BAC-32 | Context "empty" with no `CostModelMap` assignment; default also exists | GET `/reports/openshift/costs/?cost_model_context=empty` | HTTP 200; `meta.cost_model_context == "empty"` — $0 cost reported |
| [TC-94](./test-cases-t3-e2e.md#tc-94-rate-update-propagation) | BAC-27 | Default context with $10 rate; pipeline run | Update rate to $50; re-run pipeline | `cost_after / cost_before ≈ 5.0 (±0.5)` — rate propagation verified |
| [TC-95](./test-cases-t3-e2e.md#tc-95-assignment-removal-clears-context-costs) | BAC-17 | Default context with rate; pipeline run; then `CostModelMap` deleted | Re-run pipeline for "default" | All `cost_model_cpu_cost > 0` rows for context "default" are cleared |
| [TC-96](./test-cases-t3-e2e.md#tc-96-multi-tenant-isolation) | BAC-16 | Default context with rate assigned in test tenant; pipeline run | Query `OCPUsageLineItemDailySummary` in `public` schema | 0 rows or `ProgrammingError` — no cross-tenant leakage |
| [TC-97](./test-cases-t3-e2e.md#tc-97-rbac-denies-unpermitted-context-access) | BAC-29 | `CostModelContextPermission.has_permission` patched to `False` | GET `/reports/openshift/costs/?cost_model_context=default` | HTTP 403 |
| [TC-98](./test-cases-t3-e2e.md#tc-98-cross-context-isolation-via-api) | BAC-17, BAC-27 | Two contexts: "default" ($10) and "alternate" ($30); both pipelines run | GET for each context | Each response has its own `cost_model_context` in meta — cross-context isolation via API |
| [TC-99](./test-cases-t3-e2e.md#tc-99-cloud-rows-unaffected-by-context) | BAC-24 | — | Inspect `AWSCostEntryLineItemDailySummary` model | `hasattr(model, "cost_model_context")` returns `False` |
| [TC-100](./test-cases-t3-e2e.md#tc-100-ui-summary-model-has-context-field) | BAC-25 | — | Inspect `OCPCostSummaryP` model | `hasattr(model, "cost_model_context")` returns `True` |
| [TC-101](./test-cases-t3-e2e.md#tc-101-distributed-costs-tagged-with-context) | BAC-19 | Default context with rate; pipeline run | Query `OCPUsageLineItemDailySummary` for `cost_model_rate_type IN ("platform_distributed", "worker_distributed")` | All distributed rows have `cost_model_context == "default"` |

---

## 6. Pass/Fail Criteria

### 6.1 Per-Test

A test case **passes** when all assertions succeed and no unexpected
exceptions are raised.

### 6.2 Per-Phase

| Phase | Pass Criteria |
|-------|---------------|
| TDD Red | All new tests fail (or skip if SUT doesn't exist). No existing tests broken. |
| TDD Green | All new tests pass. All existing tests still pass. |
| TDD Refactor | All tests pass. Linter clean. No behavioral changes. |

### 6.3 Overall

- All 82 test cases pass
- Coverage ≥80% per tier (measured by `coverage run` + `coverage report`)
- Zero linter errors on modified files
- Zero net new regressions in existing `cost_models` and `masu.processor` suites
- All migrations forward and reverse cleanly
- All spec-vs-implementation discrepancies documented as deliberate deviations

---

## 7. Test Deliverables

| Deliverable | File | Tier |
|-------------|------|------|
| This test plan | `docs/architecture/consumer-provider-cost-models/test-plan.md` | — |
| Context model + serializer | `cost_models/test/test_cost_model_context.py` | T1 |
| Context CRUD API | `cost_models/test/test_cost_model_context_view.py` | T3 |
| Migration forward/reverse | `cost_models/test/test_context_migration.py` | T2 |
| Write-freeze guards | `cost_models/test/test_context_write_freeze.py` | T1, T2, T3 |
| Pipeline per-context | `masu/test/processor/ocp/test_context_pipeline.py` | T2, T3 |
| SQL context scoping | `masu/test/database/test_context_sql.py` | T2 |
| UI summary migrations | `masu/test/database/test_context_ui_summary.py` | T2 |
| Report API context | `api/report/test/ocp/test_context_api.py` | T1, T3 |
| RBAC permission | `api/common/permissions/test/test_context_permission.py` | T1 |
| E2E orchestration | `cost_models/test/test_context_e2e.py` | T3 |

---

## 8. Environmental Needs

### 8.1 Test Environment

- **Database**: PostgreSQL with tenant schemas (Django Tenants)
- **Schema**: Tenant schema via `MasuTestCase` / `IamTestCase`
- **Fixtures**: `baker.make()` for cost models, contexts, providers
- **Dependencies**: `model_bakery`, `unittest.mock.patch`, `rest_framework.test.APIClient`

### 8.2 Test Execution

```bash
# Run all COST-3920 tests
python manage.py test cost_models.test.test_cost_model_context \
  cost_models.test.test_cost_model_context_view \
  cost_models.test.test_context_migration \
  cost_models.test.test_context_write_freeze \
  cost_models.test.test_context_e2e \
  masu.test.processor.ocp.test_context_pipeline \
  masu.test.database.test_context_sql \
  masu.test.database.test_context_ui_summary \
  api.report.test.ocp.test_context_api \
  api.common.permissions.test.test_context_permission -v 2

# Run with coverage
coverage run --source=cost_models,masu/database/cost_model_db_accessor.py,masu/processor/tasks.py,api/report/ocp manage.py test [same modules] -v 2
coverage report --show-missing
```

---

## 9. Implementation Phases

### Phase R1: TDD Red — Context Entity + Schema (TC-01 through TC-15, TC-30 through TC-35)

**Goal**: Write failing tests for `CostModelContext` model, `CostModelMap`
constraints, `CostModelManager` context-awareness, serializer validation,
and migration forward/reverse.

**Test files**: `test_cost_model_context.py`, `test_context_migration.py`

**Exit criteria**: All tests fail or skip. No existing tests broken.

### Checkpoint C1: Red Phase Due Diligence

- Verify all BAC-1 through BAC-10 have test coverage
- Verify migration tests use raw SQL + `SET CONSTRAINTS ALL IMMEDIATE`
- Verify `information_schema` queries are schema-scoped (`AND table_schema = current_schema()`)
- Anti-pattern scan

### Phase G1: TDD Green — Context Entity + Schema

**Goal**: Make all Phase R1 tests pass. Implement model, migrations,
manager, serializer.

**Exit criteria**: All TC-01 through TC-15, TC-30 through TC-35 pass.

### Phase F1: TDD Refactor

**Exit criteria**: All tests pass. Linter clean. Code review-ready.

### Checkpoint C2: Green/Refactor Due Diligence

- Run existing `cost_models` test suite: zero regressions
- Coverage ≥80% for T1 tier
- Schema validation: `CostModelContext` table exists in all tenant schemas

### Phase R2: TDD Red — Pipeline + SQL (TC-40 through TC-62)

**Goal**: Write failing tests for accessor context filtering, SQL template
markers, cache keys, self-hosted/Trino variants, inline SQL, and
reporting table migrations.

**Test files**: `test_context_sql.py`, `test_context_ui_summary.py`, `test_context_pipeline.py`

### Checkpoint C3: Red Phase 2 Due Diligence

- Verify all 49 SQL files are covered by TC-53/TC-54 (walk-based tests)
- Verify cache key tests use `create_single_task_cache_key` directly

### Phase G2/F2: TDD Green + Refactor — Pipeline + SQL

**Exit criteria**: All TC-40 through TC-62 pass.

### Phase R3: TDD Red — API + RBAC + Write-Freeze (TC-16 through TC-23, TC-80 through TC-85, TC-WF1 through TC-WF7)

**Goal**: Write failing tests for permission logic, API parameter
acceptance, report filtering, CRUD lifecycle, and write-freeze guards.

**Test files**: `test_context_permission.py`, `test_context_api.py`,
`test_cost_model_context_view.py`, `test_context_write_freeze.py`

### Checkpoint C4: Red Phase 3 Due Diligence

- Verify permission tests cover: admin bypass, denial, pass-through, edge cases
- Verify write-freeze tests cover: create blocked, update blocked, read allowed, flag off

### Phase G3/F3: TDD Green + Refactor — API + RBAC + Write-Freeze

**Exit criteria**: All TC-16 through TC-23, TC-80 through TC-85, TC-WF1 through TC-WF7 pass.

### Phase R4/G4/F4: TDD — E2E (TC-90 through TC-101)

**Goal**: Full pipeline + API E2E tests with real DB operations.

**Test file**: `test_context_e2e.py`

### Checkpoint C5: Final Due Diligence

- Full regression run: existing cost model, accessor, and API test suites
- Coverage audit: ≥80% per tier
- Anti-pattern final scan
- Spec alignment verification: all deliberate deviations documented
- Re-run all 82 tests to confirm no flakiness

---

## 10. Risks and Contingencies

| Risk | Impact | Mitigation |
|------|--------|------------|
| R1: Migration test pending trigger events | `OperationalError: cannot ALTER TABLE` | Use raw SQL INSERT + `SET CONSTRAINTS ALL IMMEDIATE` |
| R2: Trino connection in E2E tests | `ConnectionError` on pipeline | Mock `trino_table_exists` + `schema_exists_trino` |
| R3: `information_schema` false positives | Tables from other schemas | Add `AND table_schema = current_schema()` to all `information_schema` queries |
| R4: Invalid UUID in pipeline mocks | `ValueError: badly formed UUID` | Mock `masu.processor.tasks.Provider` in write-freeze tests |
| R5: Test execution time (3× pipeline) | CI slowdown | Use targeted test discovery; parallelize per module |

---

## 11. Deliberate Deviations from Spec

| Deviation | Spec Says | Implementation Does | Rationale |
|-----------|-----------|-------------------|-----------|
| Pipeline placeholder tests | Full behavioral coverage | TC-72 through TC-76 are placeholders deferring to E2E | E2E tests (TC-90/TC-91) provide stronger assurance than mocked unit tests for pipeline ordering |
| Audit trigger test | BAC-31 requires verification | TC-57 is a placeholder | M5 audit trigger migration is proposed but not yet implemented |
| CostModelContextPermission pass-through | Spec requires gating on context | Permission returns `True` when `cost_model_context` not in query params | Prevents 403 errors on existing API clients that don't send the parameter |

---

## 12. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | — | 2026-04-09 | — |
| Reviewer | — | — | — |
| Tech Lead | — | — | — |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-08 | Initial IEEE 829 test plan |
| v2.0 | 2026-04-09 | Full rewrite: BDD Given/When/Then for all 82 test cases derived from implementation code; correct BAC-to-phase mapping; add write-freeze TCs; add test plan identifier, approval section, deliberate deviations, implementation phases with checkpoints |
| v3.0 | 2026-04-09 | IEEE 829 compliance: split detailed test case specifications into per-tier companion documents (T1/T2/T3) with full Given/When/Then blocks; test-plan.md retains summary tables with links to specs |
| v3.1 | 2026-04-09 | Add deep links from every TC identifier in summary tables to its corresponding heading in the per-tier companion documents |
