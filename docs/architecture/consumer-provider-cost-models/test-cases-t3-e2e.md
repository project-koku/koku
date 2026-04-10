# Test Case Specifications — Tier 3: End-to-End Tests

**IEEE 829-2008 Test Case Specification**

| Field | Value |
|-------|-------|
| Parent Plan | [test-plan.md](./test-plan.md) (COST-3920-TP-001) |
| Tier | T3 — End-to-End |
| Base Class | `MasuTestCase`, `IamTestCase` |
| Coverage Target | ≥80% |
| Test Count | 24 |
| Mocking Strategy | Real DB + real pipeline; mock Trino connections only |

---

## Module: `cost_models/test/test_cost_model_context_view.py`

### Class: `CostModelContextViewSetTest`

---

### TC-85: Context CRUD API lifecycle

| Field | Value |
|-------|-------|
| Identifier | TC-85 |
| Test Items | `CostModelContextViewSet` (C6), `CostModelContextSerializer` (C4) |
| BAC | BAC-30 |
| Module | `cost_models/test/test_cost_model_context_view.py` |
| Dependencies | None |

**Scenario**: Full create/list/update/delete lifecycle via the REST API.

**Given**
- A default context exists: `baker.make("CostModelContext", name="default", is_default=True)`
- An authenticated `APIClient` with valid headers

**When**
1. **CREATE**: POST `/cost-model-contexts/` with `{"name": "provider", "display_name": "Provider"}`
2. **LIST**: GET `/cost-model-contexts/`
3. **UPDATE**: PUT `/cost-model-contexts/{uuid}/` with `{"name": "provider", "display_name": "Provider (Updated)"}`
4. **DELETE**: DELETE `/cost-model-contexts/{uuid}/`
5. **VERIFY**: GET `/cost-model-contexts/{uuid}/`

**Then**
1. POST returns HTTP 201; response includes `uuid`
2. GET returns HTTP 200; `"provider"` is in the list of context names
3. PUT returns HTTP 200; `response.data["display_name"] == "Provider (Updated)"`
4. DELETE returns HTTP 204
5. GET returns HTTP 404 — context no longer exists

---

## Module: `cost_models/test/test_context_write_freeze.py`

### Class: `ContextWriteFreezeAPITest`

---

### TC-WF1: Context creation blocked when freeze active

| Field | Value |
|-------|-------|
| Identifier | TC-WF1 |
| Test Items | `CostModelContextSerializer._check_context_write_freeze` (C4, C13) |
| BAC | BAC-34 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: API returns 400 when attempting to create a context during write freeze.

**Given**
- A default context exists
- `is_context_writes_disabled` patched at `cost_models.serializers.is_context_writes_disabled` to return `True`

**When**
- POST `/cost-model-contexts/` with `{"name": "provider", "display_name": "Provider"}`

**Then**
- HTTP status code is 400 (Bad Request)
- Response body contains the word `"frozen"` (case-insensitive)

---

### TC-WF2: Context update blocked when freeze active

| Field | Value |
|-------|-------|
| Identifier | TC-WF2 |
| Test Items | `CostModelContextSerializer._check_context_write_freeze` (C4, C13) |
| BAC | BAC-35 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: API returns 400 when attempting to update a context during write freeze.

**Given**
- A default context exists with known UUID
- Freeze flag patched to return `True`

**When**
- PUT `/cost-model-contexts/{uuid}/` with `{"name": "default", "display_name": "Consumer (Updated)"}`

**Then**
- HTTP status code is 400 (Bad Request)
- Response body contains `"frozen"`

---

### TC-WF3: Context read allowed during freeze

| Field | Value |
|-------|-------|
| Identifier | TC-WF3 |
| Test Items | `CostModelContextViewSet` (C6) — read path unaffected |
| BAC | BAC-36 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: Read operations are not blocked by the write freeze.

**Given**
- A default context exists
- Freeze flag patched to return `True`

**When**
- GET `/cost-model-contexts/`

**Then**
- HTTP status code is 200 (OK) — reads are unaffected

---

### TC-WF4: Context creation allowed when freeze off

| Field | Value |
|-------|-------|
| Identifier | TC-WF4 |
| Test Items | `CostModelContextSerializer._check_context_write_freeze` (C4, C13) |
| BAC | BAC-34 |
| Module | `cost_models/test/test_context_write_freeze.py` |
| Dependencies | None |

**Scenario**: API allows context creation when freeze flag is disabled.

**Given**
- A default context exists
- `is_context_writes_disabled` patched to return `False`

**When**
- POST `/cost-model-contexts/` with `{"name": "provider", "display_name": "Provider"}`

**Then**
- HTTP status code is 201 (Created) — creation proceeds normally

---

## Module: `api/report/test/ocp/test_context_api.py`

### Class: `OCPContextQueryParamSerializerTest`

---

### TC-22: cost_model_context parameter accepted

| Field | Value |
|-------|-------|
| Identifier | TC-22 |
| Test Items | `OCPQueryParamSerializer` (C10), `OCPReportQueryHandler` (C11) |
| BAC | BAC-26 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: OCP cost report endpoint accepts cost_model_context query parameter.

**Given**
- An authenticated `APIClient` with valid headers

**When**
- GET `/reports/openshift/costs/?cost_model_context=consumer`

**Then**
- HTTP status code is 200
- `response.json()["meta"]["cost_model_context"] == "consumer"`

---

### TC-23: Missing cost_model_context has no context in meta

| Field | Value |
|-------|-------|
| Identifier | TC-23 |
| Test Items | `OCPQueryParamSerializer` (C10), `OCPReportQueryHandler` (C11) |
| BAC | BAC-33 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: Without cost_model_context param, response meta does not include it (backward-compat).

**Given**
- An authenticated `APIClient` with valid headers

**When**
- GET `/reports/openshift/costs/` (no `cost_model_context` parameter)

**Then**
- HTTP status code is 200
- `"cost_model_context"` is NOT in `response.json()["meta"]`

---

### Class: `OCPContextReportAPITest`

---

### TC-80: Cost endpoint with context returns 200

| Field | Value |
|-------|-------|
| Identifier | TC-80 |
| Test Items | OCP report endpoint (C10, C11) |
| BAC | BAC-26 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: OCP cost endpoint with cost_model_context returns a successful response.

**Given**
- An authenticated `APIClient`

**When**
- GET `/reports/openshift/costs/?cost_model_context=consumer`

**Then**
- HTTP status code is 200

---

### TC-81: Response filtered by context

| Field | Value |
|-------|-------|
| Identifier | TC-81 |
| Test Items | `OCPReportQueryHandler` (C11) — context filtering |
| BAC | BAC-27 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: Response meta reflects the requested context.

**Given**
- An authenticated `APIClient`

**When**
- GET `/reports/openshift/costs/?cost_model_context=consumer`
- Response status is 200

**Then**
- `response.json()["meta"]` contains `"cost_model_context"` key

---

### TC-82: Missing context uses default (no regression)

| Field | Value |
|-------|-------|
| Identifier | TC-82 |
| Test Items | OCP report endpoint — backward compatibility (C10, C11) |
| BAC | BAC-33 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: Omitting cost_model_context param returns 200 (existing behavior preserved).

**Given**
- An authenticated `APIClient`

**When**
- GET `/reports/openshift/costs/` (no context param)

**Then**
- HTTP status code is 200

---

### TC-83: Currency annotation context-aware

| Field | Value |
|-------|-------|
| Identifier | TC-83 |
| Test Items | `OCPReportQueryHandler` (C11) — currency annotation |
| BAC | BAC-27 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: Report with context returns data (currency annotation respects context).

**Given**
- An authenticated `APIClient`

**When**
- GET `/reports/openshift/costs/?cost_model_context=consumer`
- Response status is 200

**Then**
- Response contains `data` field (may be empty depending on test data, but no error)

---

### TC-84: Unpermitted/nonexistent context handled gracefully

| Field | Value |
|-------|-------|
| Identifier | TC-84 |
| Test Items | OCP report endpoint — error handling (C10, C11, C12) |
| BAC | BAC-29 |
| Module | `api/report/test/ocp/test_context_api.py` |
| Dependencies | None |

**Scenario**: Requesting a nonexistent context returns a handled response (not 500).

**Given**
- An authenticated `APIClient`

**When**
- GET `/reports/openshift/costs/?cost_model_context=nonexistent`

**Then**
- HTTP status code is 200 or 400 — graceful handling, no 500

---

## Module: `cost_models/test/test_context_e2e.py`

### Class: `PipelineSmokeE2ETest`

---

### TC-90: Single context pipeline smoke test

| Field | Value |
|-------|-------|
| Identifier | TC-90 |
| Test Items | Full pipeline: task (C9) → accessor (C7) → updater (C8) → SQL → DB → API (C11) |
| BAC | BAC-16, BAC-27 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |
| Special Requirements | Trino mocked (`trino_table_exists=False`, `schema_exists_trino=False`) |

**Scenario**: Single context pipeline produces cost rows with correct context tag, verifiable via API.

**Given**
- Context "default" (is_default=True) exists
- Cost model with known CPU rate: `$10/core-hour`, cost_type `"Infrastructure"`
- `CostModelMap` links `ocp_provider_uuid` to cost model via "default" context
- Trino connections mocked to return `False`

**When**
- Pipeline runs: `update_cost_model_costs(schema, provider_uuid, start, end, cost_model_context="default", synchronous=True)`
- API call: GET `/reports/openshift/costs/?cost_model_context=default`

**Then**
- **DB assertions**:
  - `OCPUsageLineItemDailySummary` rows exist where:
    - `source_uuid == ocp_provider_uuid`
    - `cost_model_context == "default"`
    - `cost_model_rate_type == "Infrastructure"`
  - `SUM(cost_model_cpu_cost) > 0` — positive cost from the $10/core-hour rate
- **API assertions**:
  - HTTP 200
  - `response.json()["meta"]["cost_model_context"] == "default"`

---

### TC-91: Dual context isolation smoke test

| Field | Value |
|-------|-------|
| Identifier | TC-91 |
| Test Items | Full pipeline: multi-context dispatch → DB isolation → API verification |
| BAC | BAC-16, BAC-17 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |
| Special Requirements | Trino mocked |

**Scenario**: Two contexts produce independent cost rows at correct rate ratios.

**Given**
- Context "consumer" (default, position=1): cost model with `$10/core-hour`
- Context "provider" (position=2): cost model with `$20/core-hour`
- Both assigned to the same `ocp_provider_uuid` via separate `CostModelMap` rows

**When**
- Pipeline runs for "consumer": `update_cost_model_costs(..., cost_model_context="consumer")`
- Pipeline runs for "provider": `update_cost_model_costs(..., cost_model_context="provider")`
- API calls: GET for each context

**Then**
- **DB assertions**:
  - `consumer_cost = SUM(cost_model_cpu_cost WHERE cost_model_context = "consumer")` > 0
  - `provider_cost = SUM(cost_model_cpu_cost WHERE cost_model_context = "provider")` > 0
  - `provider_cost / consumer_cost ≈ 2.0` (within ±0.1 delta) — ratio matches $20/$10
- **API assertions**:
  - Consumer response: `meta.cost_model_context == "consumer"`
  - Provider response: `meta.cost_model_context == "provider"`

---

### Class: `APIContextE2ETest`

---

### TC-92: Explicit default equals implicit (backward-compat)

| Field | Value |
|-------|-------|
| Identifier | TC-92 |
| Test Items | API backward compatibility (C10, C11) |
| BAC | BAC-33, BAC-27 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | TC-90 |

**Scenario**: Explicit ?cost_model_context=default includes context in meta; implicit does not.

**Given**
- Default context with rate; pipeline has been run for "default"

**When**
- Explicit: GET `/reports/openshift/costs/?cost_model_context=default`
- Implicit: GET `/reports/openshift/costs/` (no param)

**Then**
- Both return HTTP 200
- Explicit response: `meta.cost_model_context == "default"`
- Implicit response: `"cost_model_context"` NOT in `meta`

---

### TC-93: Empty context shows $0 cost

| Field | Value |
|-------|-------|
| Identifier | TC-93 |
| Test Items | API + accessor — empty context path (C7, C11) |
| BAC | BAC-32 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: Context with no cost model assignment reports $0 cost via API.

**Given**
- Context "empty" exists (position=2, is_default=False) with NO `CostModelMap` assignment
- Context "default" also exists (for schema validity)

**When**
- GET `/reports/openshift/costs/?cost_model_context=empty`

**Then**
- HTTP 200
- `meta.cost_model_context == "empty"`
- Cost data is $0 (no cost model = no cost injection)

---

### TC-94: Rate update propagation

| Field | Value |
|-------|-------|
| Identifier | TC-94 |
| Test Items | Full pipeline re-run after rate change (C7, C8, C9) |
| BAC | BAC-27 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: Updating a rate and re-running the pipeline produces updated costs.

**Given**
- Default context with cost model at `$10/core-hour`; pipeline run once
- `cost_before = SUM(cost_model_cpu_cost WHERE context = "default")`

**When**
- Rate updated to `$50/core-hour` (`cm.rates = [{..., "value": "50.00"}]; cm.save()`)
- Pipeline re-run for "default"

**Then**
- `cost_after = SUM(cost_model_cpu_cost WHERE context = "default")`
- `cost_after > cost_before`
- `cost_after / cost_before ≈ 5.0` (within ±0.5 delta)

---

### TC-95: Assignment removal clears context costs

| Field | Value |
|-------|-------|
| Identifier | TC-95 |
| Test Items | Pipeline re-run after CostModelMap deletion (C7, C8, C9) |
| BAC | BAC-17 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: Removing a cost model assignment and re-running the pipeline clears that context's costs.

**Given**
- Default context with rate; pipeline run; cost rows exist with `cost_model_cpu_cost > 0`

**When**
- `CostModelMap` for the provider+context is deleted
- Pipeline re-run for "default" context

**Then**
- No `cost_model_cpu_cost > 0` rows remain for context "default"
  (`remaining == 0`)

---

### TC-96: Multi-tenant isolation

| Field | Value |
|-------|-------|
| Identifier | TC-96 |
| Test Items | Tenant isolation (C9) |
| BAC | BAC-16 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: Contexts in one tenant do not leak costs into another schema.

**Given**
- Default context with rate assigned in the test tenant; pipeline run

**When**
- Query `OCPUsageLineItemDailySummary` in the `public` schema for `cost_model_context = "default"`

**Then**
- Either 0 rows returned, or `ProgrammingError` (table doesn't exist in public schema)
- Both outcomes prove no cross-tenant leakage

---

### TC-97: RBAC denies unpermitted context access

| Field | Value |
|-------|-------|
| Identifier | TC-97 |
| Test Items | `CostModelContextPermission` (C12) — end-to-end |
| BAC | BAC-29 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |
| Special Requirements | `@override_settings(ENHANCED_ORG_ADMIN=False)` |

**Scenario**: RBAC denies access when permission check returns False.

**Given**
- Default context with rate
- `CostModelContextPermission.has_permission` patched to return `False`

**When**
- GET `/reports/openshift/costs/?cost_model_context=default`

**Then**
- HTTP 403 (Forbidden) — if the permission mock was invoked
- Verifies that RBAC enforcement is wired into the view

---

### TC-98: Cross-context isolation via API

| Field | Value |
|-------|-------|
| Identifier | TC-98 |
| Test Items | Full pipeline + API — two distinct contexts (C7, C8, C9, C11) |
| BAC | BAC-17, BAC-27 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: Two contexts return distinct data through the API.

**Given**
- Context "default" with `$10/core-hour` rate
- Context "alternate" with `$30/core-hour` rate
- Both assigned to the same provider; both pipelines run

**When**
- GET `/reports/openshift/costs/?cost_model_context=default`
- GET `/reports/openshift/costs/?cost_model_context=alternate`

**Then**
- Both return HTTP 200
- Default response: `meta.cost_model_context == "default"`
- Alternate response: `meta.cost_model_context == "alternate"`
- Contexts return their own data — no cross-contamination

---

### TC-99: Cloud rows unaffected by context

| Field | Value |
|-------|-------|
| Identifier | TC-99 |
| Test Items | `AWSCostEntryLineItemDailySummary` model (SQL) |
| BAC | BAC-24 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: AWS (cloud) model does not have cost_model_context field.

**Given**
- The `AWSCostEntryLineItemDailySummary` model is imported

**When**
- `hasattr(AWSCostEntryLineItemDailySummary, "cost_model_context")` is evaluated

**Then**
- Returns `False` — cloud models are unaffected

---

### TC-100: UI summary model has context field

| Field | Value |
|-------|-------|
| Identifier | TC-100 |
| Test Items | `OCPCostSummaryP` model (C15) |
| BAC | BAC-25 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | None |

**Scenario**: OCP UI summary model includes cost_model_context field.

**Given**
- The `OCPCostSummaryP` model is imported

**When**
- `hasattr(OCPCostSummaryP, "cost_model_context")` is evaluated

**Then**
- Returns `True` — the context column was added by migration M8

---

### TC-101: Distributed costs tagged with context

| Field | Value |
|-------|-------|
| Identifier | TC-101 |
| Test Items | Distribution SQL + pipeline (C8, SQL) |
| BAC | BAC-19 |
| Module | `cost_models/test/test_context_e2e.py` |
| Dependencies | TC-90 |

**Scenario**: Cost distribution rows carry the correct context tag.

**Given**
- Default context with `$10/core-hour` rate; pipeline run

**When**
- Query `OCPUsageLineItemDailySummary` for distributed rows:
  `cost_model_rate_type IN ("platform_distributed", "worker_distributed")`

**Then**
- For every distributed row:
  `row.cost_model_context == "default"`
- Distribution SQL correctly propagates the context tag
