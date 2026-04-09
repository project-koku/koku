# Test Plan — COST-3920 Consumer-Provider Cost Models

**Parent**: [README.md](README.md) · **Status**: Design Proposal
**Template**: IEEE 829-2008

---

## 1. Introduction

### 1.1 Purpose

This test plan defines the verification and validation strategy for
COST-3920 (Consumer-Provider Cost Models). It covers all phases of
the feature with behavioral acceptance criteria, following koku
testing conventions.

### 1.2 Scope

Tests will cover:
- Context entity CRUD (model, serializer, viewset)
- Assignment with context (CostModelMap, manager)
- Schema migrations (forward/reverse, data migration, backfill)
- Per-context pipeline execution (accessor, updater, SQL templates)
- API integration (query parameter, response filtering)
- RBAC (Koku-side authorization, context permission)
- Write-freeze guards (Unleash flag, serializer, pipeline)
- Cross-context data isolation

### 1.3 Definitions

| Term | Definition |
|------|-----------|
| **Context** | A `CostModelContext` instance (e.g., "Consumer", "Provider") |
| **BAC** | Business Acceptance Criterion |
| **TC** | Test Case |
| **TDD** | Test-Driven Development (Red/Green/Refactor) |

---

## 2. Test Items

### 2.1 Models Layer (6 components)

- `CostModelContext` — **NEW**
- `CostModelMap` + `cost_model_context` FK — **MODIFIED**
- Migrations M1-M7 — **NEW** (cost_models + reporting)
- `reporting_ocpusagelineitem_daily_summary` + `cost_model_context` — **MODIFIED**
- 13 `reporting_ocp_*_summary_p` tables + `cost_model_context` — **MODIFIED**
- `CostModelAudit` trigger — **MODIFIED**

### 2.2 Manager + Serializer Layer (4 components)

- `CostModelManager.update_provider_uuids` — **MODIFIED**
- `CostModelSerializer.create/update` — **MODIFIED**
- `CostModelContextSerializer` — **NEW**
- `CostModelContextViewSet` — **NEW**

### 2.3 Pipeline Layer (6 components)

- `CostModelDBAccessor.cost_model` — **MODIFIED**
- `OCPCostModelCostUpdater` — **MODIFIED**
- `update_cost_model_costs` task + cache key — **MODIFIED**
- `OCPReportDBAccessor.populate_ui_summary_tables` — **MODIFIED**
- Distribution SQL orchestration — **MODIFIED**
- `TableExportSetting` — **MODIFIED**

### 2.4 SQL Layer (49+ artifacts)

- 16 cost model SQL (`sql/openshift/cost_model/`)
- 9 self-hosted cost model SQL (`self_hosted_sql/openshift/cost_model/`)
- 9 Trino cost model SQL (`trino_sql/openshift/cost_model/`)
- 13 UI summary SQL (`sql/openshift/ui_summary/`)
- 2 UI summary usage-only variants (self-hosted + Trino)

### 2.5 API + RBAC Layer (6 components)

- `OCPQueryParamSerializer` — **MODIFIED**
- `OCPProviderMap` — **MODIFIED**
- `CostModelContextPermission` — **NEW**
- `OCPReportQueryHandler` — **MODIFIED**
- Currency annotation — **MODIFIED**
- `CostModelContextView` — **NEW**

### 2.6 Write-Freeze Layer (3 components)

- `is_context_writes_disabled()` — **NEW** (`masu/processor/__init__.py`)
- `CostModelContextSerializer._check_context_write_freeze()` — **NEW**
- `update_cost_model_costs` pipeline guard — **MODIFIED**

---

## 3. Business Acceptance Criteria (38 BACs)

### Phase 1 — Context Entity + Schema (10 BACs)

| BAC | Description |
|-----|------------|
| BAC-1 | `CostModelContext.objects.create()` succeeds with valid name/display_name |
| BAC-2 | Max 3 contexts per tenant enforced (4th creation raises `ValidationError`) |
| BAC-3 | Exactly one default context per tenant (partial unique index on `is_default=TRUE`) |
| BAC-4 | Default context cannot be deleted (raises `ValidationError`) |
| BAC-5 | `CostModelMap` accepts multiple rows for same provider with different contexts |
| BAC-6 | `CostModelMap` rejects duplicate `(provider_uuid, cost_model_context)` pair (DB `IntegrityError`) |
| BAC-7 | `update_provider_uuids` allows same provider in different contexts |
| BAC-8 | `update_provider_uuids` rejects same provider+context twice (descriptive error) |
| BAC-9 | Data migration creates default "Consumer" context per tenant schema |
| BAC-10 | Data migration assigns all existing `CostModelMap` rows to default context |

### Phase 2 — Reporting Schema + Backfill (12 BACs)

| BAC | Description |
|-----|------------|
| BAC-11 | `CostModelDBAccessor(context=X)` returns correct cost model for that context |
| BAC-12 | `CostModelDBAccessor(context=None)` falls back to `.first()` (backward-compatible) |
| BAC-13 | Pipeline executes per-context with context-specific rates |
| BAC-14 | SQL DELETE scopes by `cost_model_context` — does NOT delete other contexts' rows |
| BAC-15 | SQL INSERT includes `cost_model_context` value in all new rows |
| BAC-16 | UI summary DELETE scopes by `cost_model_context` — prevents cross-context data loss |
| BAC-17 | UI summary GROUP BY includes `cost_model_context` |
| BAC-18 | Distribution SQL scopes by `cost_model_context` |
| BAC-19 | Celery cache key includes context — allows parallel per-context tasks |
| BAC-20 | Self-hosted SQL variants include `cost_model_context` in all DML |
| BAC-21 | Python inline SQL handles context parameter |
| BAC-22 | Cloud rows (`cost_model_rate_type = NULL`) are untouched by context scoping |

### Phase 3 — Pipeline + SQL (6 BACs)

| BAC | Description |
|-----|------------|
| BAC-23 | `cost_model_context` query parameter accepted on all OCP report endpoints |
| BAC-24 | Report response filters cost data by requested context |
| BAC-25 | `CostModelContextPermission` allows admin bypass (`ENHANCED_ORG_ADMIN`) |
| BAC-26 | `CostModelContextPermission` denies access to unpermitted contexts |
| BAC-27 | Currency annotation joins through context-specific `CostModelMap` row |
| BAC-28 | Report views enforce context visibility (when context explicitly requested) |

### Phase 4 — API + RBAC (3 BACs)

| BAC | Description |
|-----|------------|
| BAC-29 | Audit trigger captures context array alongside provider_uuids |
| BAC-30 | Empty context (no cost model) shows usage at $0 cost |
| BAC-31 | Backfill migration sets `cost_model_context = 'default'` on all cost-model rows |

### Phase 5 — Write-Freeze + Data Consistency (7 BACs)

| BAC | Description |
|-----|------------|
| BAC-32 | Context creation returns 400 when write-freeze Unleash flag is active |
| BAC-33 | Context update returns 400 when write-freeze flag is active |
| BAC-34 | Context read/list succeeds during write-freeze (reads are not blocked) |
| BAC-35 | Context creation succeeds when write-freeze flag is disabled |
| BAC-36 | Pipeline skips context-tagged writes when write-freeze is active |
| BAC-37 | Pipeline executes normally when write-freeze flag is disabled |
| BAC-38 | Pipeline runs for None context (legacy path) without triggering write-freeze guard |

---

## 4. Approach

### 4.1 Test Tiers

| Tier | Description | Base Class | Coverage Target |
|------|-------------|------------|-----------------|
| T1: Unit | Model validation, serializer logic, permission checks, manager guards | `IamTestCase` | >=85% |
| T2: Integration | SQL execution, accessor methods, migration forward/reverse, DB constraints | `MasuTestCase` | >=80% |
| T3: E2E | End-to-end orchestration, API request/response, pipeline order, cross-context isolation | `MasuTestCase` | >=80% |

### 4.2 TDD Process

Each test case follows Red/Green/Refactor:

1. **Red**: Write failing test that asserts expected BAC behavior
2. **Green**: Write minimal implementation to make the test pass
3. **Refactor**: Clean up code; verify tests still pass; lint check

### 4.3 Anti-Pattern Avoidance

Following koku testing conventions:
- Use `baker.make()` not `Model.objects.create()`
- Use parenthesized `with (patch(...), patch(...)):` not nested `with`
- Use `schema_context` + `subTest` for multi-scenario
- Assert param dicts and table names, not SQL strings
- Each test opens its own accessor context manager
- Test via public API; private method tests only where business logic requires
- Deterministic rate values; reserve random for property-based tests

---

## 5. Test Cases (104 total)

### T1: Unit Tests (~35 test cases)

| TC | BAC | Description |
|----|-----|------------|
| TC-01 | BAC-1 | Create context with valid name and display_name |
| TC-02 | BAC-1 | Context name uniqueness per tenant |
| TC-03 | BAC-2 | Fourth context creation raises ValidationError |
| TC-04 | BAC-3 | Two default contexts raises IntegrityError (partial unique index) |
| TC-05 | BAC-4 | Delete default context raises ValidationError |
| TC-06 | BAC-5 | CostModelMap allows same provider with different contexts |
| TC-07 | BAC-6 | CostModelMap rejects duplicate (provider_uuid, context) |
| TC-08 | BAC-7 | update_provider_uuids allows same provider in different contexts |
| TC-09 | BAC-8 | update_provider_uuids rejects same provider+context (descriptive error) |
| TC-10 | BAC-2 | Position CHECK constraint (1-3) on CostModelContext |
| TC-11 | BAC-25 | CostModelContextPermission allows ENHANCED_ORG_ADMIN |
| TC-12 | BAC-26 | CostModelContextPermission denies when no cost_model.read access |
| TC-13 | BAC-26 | CostModelContextPermission passes when cost_model_context not in query_params |
| TC-14 | BAC-23 | OCPQueryParamSerializer accepts cost_model_context parameter |
| TC-15 | BAC-23 | OCPQueryParamSerializer validates cost_model_context length |
| TC-16 | BAC-32 | CostModelContextSerializer._check_context_write_freeze blocks create |
| TC-17 | BAC-33 | CostModelContextSerializer._check_context_write_freeze blocks update |
| TC-18 | BAC-34 | Context list/retrieve succeeds during write-freeze |
| TC-19 | BAC-35 | Context create succeeds when freeze flag is disabled |
| TC-20 | BAC-30 | Empty context returns zero cost (no cost model assigned) |
| TC-21 | BAC-4 | Delete non-default context succeeds |
| TC-22 | BAC-1 | CostModelContext display_name max_length enforcement |
| TC-23 | BAC-3 | Setting new default also unsets old default |
| TC-24 | BAC-6 | CostModelMap null context (legacy row) coexists with named contexts |
| TC-25 | BAC-27 | Currency annotation uses context-specific cost model currency |
| TC-26 | BAC-28 | Report view denies when context explicitly requested and user lacks access |
| TC-27 | BAC-28 | Report view allows when context not in query params (pass-through) |
| TC-28 | BAC-1 | Context CRUD API: POST /api/v1/cost-model-contexts/ |
| TC-29 | BAC-1 | Context CRUD API: GET /api/v1/cost-model-contexts/ |
| TC-30 | BAC-1 | Context CRUD API: PUT /api/v1/cost-model-contexts/{uuid}/ |
| TC-31 | BAC-9 | Migration forward: default context created per tenant |
| TC-32 | BAC-10 | Migration forward: existing CostModelMap rows assigned default context |
| TC-33 | BAC-9 | Migration reverse: context removed cleanly |
| TC-34 | BAC-31 | Backfill migration: cost_model_context = 'default' on daily summary |
| TC-35 | BAC-31 | Backfill migration: cost_model_context = 'default' on all 13 UI summary tables |

### T2: Integration Tests (~40 test cases)

| TC | BAC | Description |
|----|-----|------------|
| TC-36 | BAC-11 | CostModelDBAccessor(context='consumer') returns consumer's cost model |
| TC-37 | BAC-11 | CostModelDBAccessor(context='provider') returns provider's cost model |
| TC-38 | BAC-12 | CostModelDBAccessor(context=None) returns first cost model |
| TC-39 | BAC-14 | SQL DELETE scopes by cost_model_context (standard path) |
| TC-40 | BAC-14 | SQL DELETE scopes by cost_model_context (self-hosted path) |
| TC-41 | BAC-14 | SQL DELETE scopes by cost_model_context (Trino path) |
| TC-42 | BAC-15 | SQL INSERT includes cost_model_context in output rows |
| TC-43 | BAC-16 | UI summary DELETE scopes by cost_model_context |
| TC-44 | BAC-17 | UI summary GROUP BY includes cost_model_context |
| TC-45 | BAC-18 | Distribution SQL passes cost_model_context parameter |
| TC-46 | BAC-20 | Self-hosted SQL variants include cost_model_context |
| TC-47 | BAC-21 | Python inline SQL DELETE handles cost_model_context |
| TC-48 | BAC-22 | Cloud rows (rate_type NULL) unaffected by context scoping |
| TC-49 | BAC-13 | Pipeline produces correct cost values for context 'consumer' |
| TC-50 | BAC-13 | Pipeline produces correct cost values for context 'provider' |
| TC-51 | BAC-14 | Context A pipeline run does not delete context B rows |
| TC-52 | BAC-19 | Worker cache key includes cost_model_context |
| TC-53 | BAC-29 | Audit trigger includes context in audit row |
| TC-54 | BAC-36 | Pipeline task returns early when write-freeze active and context is set |
| TC-55 | BAC-37 | Pipeline task runs updater when write-freeze is disabled |
| TC-56 | BAC-38 | Pipeline task runs for None context regardless of write-freeze |
| TC-57 | BAC-31 | Backfill migration reverse: cost_model_context set back to NULL |
| TC-58-70 | BAC-15 | SQL template parameter assertions for each of 13 UI summary SQL files |
| TC-71-75 | BAC-14 | SQL template DELETE WHERE assertions (5 cost model SQL categories) |

### T3: E2E Tests (~29 test cases)

| TC | BAC | Description |
|----|-----|------------|
| TC-76 | BAC-13 | Full pipeline run: create 2 contexts, assign cost models, run pipeline, verify per-context rows in daily summary |
| TC-77 | BAC-14 | Full pipeline run: verify re-run for context A does not affect context B |
| TC-78 | BAC-24 | API request with cost_model_context=consumer returns only consumer cost data |
| TC-79 | BAC-24 | API request without cost_model_context returns all cost data |
| TC-80 | BAC-19 | Parallel context tasks: dispatch 2 tasks for same provider, different contexts — both complete without cache collision |
| TC-81 | BAC-9 | Migration E2E: fresh tenant gets default context + assignment |
| TC-82 | BAC-22 | Cloud infrastructure costs appear in all context responses unchanged |
| TC-83 | BAC-30 | Context with no cost model: API returns usage at $0 |
| TC-84 | BAC-16 | UI summary: two contexts produce distinct rollup rows |
| TC-85 | BAC-17 | UI summary: GROUP BY context produces correct aggregation |
| TC-86 | BAC-25 | Admin user accesses all contexts via API |
| TC-87 | BAC-26 | Non-admin user denied context access when lacking cost_model.read |
| TC-88 | BAC-32 | API POST /cost-model-contexts/ returns 400 during write-freeze |
| TC-89 | BAC-33 | API PUT /cost-model-contexts/{uuid}/ returns 400 during write-freeze |
| TC-90 | BAC-34 | API GET /cost-model-contexts/ succeeds during write-freeze |
| TC-91 | BAC-36 | Pipeline skip during write-freeze: no new rows inserted |
| TC-92 | BAC-10 | Assignment migration: multi-provider tenant gets all CostModelMap rows updated |
| TC-93 | BAC-31 | Backfill E2E: daily summary + 13 UI tables all backfilled correctly |
| TC-94 | BAC-8 | API assign same provider+context twice returns descriptive error |
| TC-95 | BAC-4 | API DELETE default context returns 400 with descriptive error |
| TC-96 | BAC-13 | Multi-tenant isolation: tenant A's contexts do not leak to tenant B |
| TC-97 | BAC-18 | Distribution with context: platform/worker costs distributed per-context |
| TC-98-104 | Various | Regression tests for existing cost model functionality (no regressions from context changes) |

---

## 6. Pass/Fail Criteria

- All T1 tests pass (unit)
- All T2 tests pass (integration)
- All T3 tests pass (E2E)
- Zero net new regressions in existing `cost_models` test suite
- Zero net new regressions in existing `masu.processor` test suite
- Coverage per tier >= 80% of testable code
- All migrations are reversible

---

## 7. Test Deliverables

### Proposed test files

| File | Scope | Tier |
|------|-------|------|
| `cost_models/test/test_cost_model_context.py` | Context model, serializer, max 3, default protection | T1 |
| `cost_models/test/test_cost_model_context_view.py` | Context CRUD API | T1, T3 |
| `cost_models/test/test_context_assignment.py` | Manager per-context, CostModelMap constraints | T1, T2 |
| `cost_models/test/test_context_migration.py` | Forward/reverse migration, per-tenant data migration | T2 |
| `cost_models/test/test_context_write_freeze.py` | Write-freeze API and pipeline guards | T1, T2, T3 |
| `masu/test/processor/ocp/test_context_pipeline.py` | Per-context pipeline orchestration, concurrency | T2, T3 |
| `masu/test/database/test_context_sql.py` | SQL context scoping (standard, self-hosted, Trino) | T2 |
| `masu/test/database/test_context_ui_summary.py` | UI summary cross-context isolation | T2, T3 |
| `api/report/test/ocp/test_context_api.py` | Report API with context parameter | T1, T3 |
| `api/common/permissions/test_context_permission.py` | Hybrid RBAC, edge cases | T1 |
| `cost_models/test/test_context_e2e.py` | Full pipeline E2E orchestration | T3 |

---

## 8. Environmental Needs

- PostgreSQL with tenant schemas (Django Tenants)
- `MasuTestCase` / `IamTestCase` test infrastructure
- `model_bakery` for fixture creation
- `unittest.mock.patch` for Unleash flag mocking
- No Trino required (Trino paths mocked in tests)

---

## 9. Risks and Contingencies

| Risk | Impact | Contingency |
|------|--------|------------|
| Test execution time increase (3× pipeline runs) | CI slowdown | Parallelize per-context tests; use targeted test discovery |
| Migration test fragility | Flaky CI | Use raw SQL + `SET CONSTRAINTS ALL IMMEDIATE` pattern |
| Trino connection in tests | Test failure | Mock `trino_table_exists` and `schema_exists_trino` |

---

## 10. Deployment Strategy

**TL requirement**: Migrations are split from business logic in
separate commits. Migrations deploy first; business logic rolls out
incrementally after.

Each phase produces **two commit groups**:
1. **Migration commit** — DDL only. Must be backward-compatible with current code.
2. **Logic commit(s)** — Python code changes. Can be reverted independently.

**Backward-compatibility constraint**: Migrations must not break
existing code. This is why `cost_model_context` is nullable
(`NULL` = default) — existing code that doesn't pass a context
continues to work against the new schema.

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-08 | Initial IEEE 829 test plan: 97 test cases, 30 BACs |
| v2.0 | 2026-04-09 | Design proposal: added write-freeze BACs (32-38), write-freeze TCs (88-91), updated test deliverables with `test_context_write_freeze.py`, expanded to 104 test cases and 38 BACs |
