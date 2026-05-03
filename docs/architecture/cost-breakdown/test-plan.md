# Test Plan — COST-7249 Phase 1: Schema Normalization

**IEEE 829 Format** | Version 1.0 | 2026-04-06

---

## 1. Test Plan Identifier

`TP-COST-7249-P1-v1.0`

---

## 2. References

| ID | Document | Location |
|----|----------|----------|
| REF-1 | Cost breakdown technical design | `docs/architecture/cost-breakdown/README.md` |
| REF-2 | Data model spec | `docs/architecture/cost-breakdown/data-model.md` |
| REF-3 | API and frontend spec | `docs/architecture/cost-breakdown/api-and-frontend.md` |
| REF-4 | Phased delivery plan | `docs/architecture/cost-breakdown/phased-delivery.md` |
| REF-5 | Risk register | `docs/architecture/cost-breakdown/risk-register.md` |
| REF-6 | Concerns register | `docs/architecture/cost-breakdown/open-concerns.md` |
| REF-7 | COST-575 PR #5957 | Migration 0011: CostModel → PriceList data migration |
| REF-8 | COST-575 PR #5963 | Dual-write CostModel rates to PriceList |
| REF-9 | Tech lead gist | Migration coordination / dual-write strategy |
| REF-10 | Design PR #5980 | Alignment with COST-575 (approved, pending merge) |

---

## 3. Introduction

Phase 1 normalizes rate storage from a JSON blob (`CostModel.rates`)
into a relational `Rate` table, introduces diff-based synchronization
(`_sync_rate_table`), and adds an Unleash write-freeze flag for
migration safety. This test plan covers all Phase 1 deliverables.

### 3.1 Scope

| In Scope | Out of Scope |
|----------|-------------|
| `Rate` Django model (M1 DDL) | `RatesToUsage` model (Phase 2) |
| Data migration M2 (JSON → Rate rows) | SQL pipeline changes (Phase 2-3) |
| Diff-based `_sync_rate_table()` | Breakdown API/UI (Phase 4) |
| `RateSerializer` updates (`rate_id`, `custom_name`) | JSON column drop (Phase 5) |
| Unleash write-freeze flag + serializer gating | Frontend `rate_id` support (separate PR) |
| Helper functions (`generate_custom_name`, `derive_metric_type`, `extract_default_rate`) | `CostModelDBAccessor` read-path changes (Phase 1b) |

---

## 4. Test Items

| ID | Item | Source File(s) | Priority |
|----|------|---------------|----------|
| TI-1 | `Rate` model | `cost_models/models.py` | P0 |
| TI-2 | Migration 0012 (Rate DDL) | `cost_models/migrations/0012_*.py` | P0 |
| TI-3 | Migration 0013 (data migration) | `cost_models/migrations/0013_*.py` | P0 |
| TI-4 | `generate_custom_name()` | `cost_models/cost_model_manager.py` | P0 |
| TI-5 | `derive_metric_type()` | `cost_models/cost_model_manager.py` | P0 |
| TI-6 | `extract_default_rate()` | `cost_models/cost_model_manager.py` | P0 |
| TI-7 | `RateSerializer` (`rate_id`, `custom_name`, `to_representation`) | `cost_models/serializers.py` | P0 |
| TI-8 | `_sync_rate_table()` (diff-based sync) | `cost_models/cost_model_manager.py` | P0 |
| TI-9 | `_apply_rate_fields()`, `_rate_fields_from_data()` | `cost_models/cost_model_manager.py` | P1 |
| TI-10 | `is_cost_model_writes_disabled()` | `masu/processor/__init__.py` | P0 |
| TI-11 | Write-freeze gating in `CostModelSerializer` | `cost_models/serializers.py` | P0 |
| TI-12 | Integration: create → sync → GET round-trip | Multiple | P0 |
| TI-13 | Integration: update → diff-sync → GET round-trip | Multiple | P0 |

---

## 5. Software Risk Issues — Pre-Implementation Due Diligence

The following findings were identified by tracing the actual codebase
against the design specifications. Each finding has a severity, impact
assessment, and resolution that is incorporated into the implementation
phases below.

### F1: `related_name="rates"` conflicts with `PriceList.rates` JSONField

**Severity**: BLOCKER (Django will refuse to create the model)

**Evidence**: `PriceList` has `rates = JSONField()` (line 137,
`models.py`). The design doc's `Rate` model specifies
`related_name="rates"` on the `price_list` FK. Django raises
`SystemCheckError` when a reverse relation name collides with an
existing field.

**Resolution**: Use `related_name="rate_rows"`. The `_sync_rate_table`
pseudocode already uses `price_list.rate_rows.all()`, confirming this
was the intended name.

### F2: Design doc `PriceList` schema diverges from COST-575 implementation

**Severity**: HIGH (wrong FK target, wrong table name)

**Evidence**: `data-model.md` § New Models describes `PriceList` with
`db_table = "cost_model_price_list"`, a direct `cost_model` FK, and
`primary`/`fallback` fields. The actual `PriceList` (COST-575, line
109, `models.py`) uses `db_table = "price_list"`, has `name`,
`description`, `currency`, date fields, and links via
`PriceListCostModelMap` junction table.

**Resolution**: Implementation follows the COST-575 code, not the
pre-alignment data-model.md. The Rate model's FK points to the
existing `PriceList`. Migration M2 iterates `PriceListCostModelMap`
entries. The design PR (#5980) updated `api-and-frontend.md` and
`open-concerns.md` to reflect this alignment.

### F3: `tag_values` default should be `list` not `dict`

**Severity**: MEDIUM (incorrect default, data shape mismatch)

**Evidence**: Design doc specifies `tag_values = JSONField(default=dict)`.
Actual tag rate data in `CostModel.rates` stores `tag_values` as a list
of dicts: `[{"tag_value": "smoke", "value": 123, ...}]`. Gemini
code-assist flagged this (PR #5980 review).

**Resolution**: Use `JSONField(default=list)` in the Rate model and
migration. Tests must verify both empty default and populated list.

### F4: `default_rate` extraction ignores tag rates

**Severity**: MEDIUM (tag-based rates get `default_rate=0`)

**Evidence**: M2 migration pseudocode extracts `default_rate` from
`tiered_rates[0].get("value", 0)`. For tag-based rates, `tiered_rates`
is empty/absent — the default rate should come from the tag_values
entry where `default=True`.

**Resolution**: `extract_default_rate()` checks `tiered_rates` first,
then falls back to the default tag value. Tests cover both paths.

### F5: M2 migration uses `create()` in loop instead of `bulk_create`

**Severity**: LOW (performance, not correctness)

**Evidence**: M2 pseudocode calls `Rate.objects.create()` per rate
inside the mapping loop. Gemini code-assist flagged this.

**Resolution**: Collect Rate instances per mapping, `bulk_create` after
the loop. Must still inject `rate_id` back — `bulk_create` returns
objects with populated PKs (Django 4.2+, PostgreSQL).

### F6: `auto_now` field not in `update_fields` for second save

**Severity**: LOW (timestamp slightly stale, not incorrect)

**Evidence**: `_sync_rate_table` calls
`self._model.save(update_fields=["rates"])` which does NOT update
`updated_timestamp` (Django's `auto_now` requires explicit inclusion
in `update_fields`). However, `update()` calls `self._model.save()`
(no `update_fields`) immediately before, which DOES update the
timestamp. The second save is moments later — the timestamp is at most
milliseconds stale.

**Resolution**: Acceptable. The first save in `update()` sets the
authoritative timestamp. Document the two-save pattern in code
comments. If precision matters, add `"updated_timestamp"` to the
second save's `update_fields`.

### F7: Redundant PriceList save in `update()` flow

**Severity**: LOW (extra DB write, not incorrect)

**Evidence**: `update()` saves `pl.rates` directly, then calls
`_sync_rate_table()` which saves `pl.rates` again (with `rate_id`
injected). Two PriceList writes per update.

**Resolution**: Remove the direct PriceList save from `update()`. Let
`_sync_rate_table()` handle the final save after `rate_id` injection.
The `create()` flow is clean (no pre-save).

### F8: Monthly/node/cluster/PVC metrics absent from `USAGE_METRIC_MAP`

**Severity**: MEDIUM (unmapped metrics → `derive_metric_type` fails)

**Evidence**: `USAGE_METRIC_MAP` (line 323, `constants.py`) only maps 9
usage-hour/storage-month metrics. Monthly cost metrics like
`node_cost_per_month`, `cluster_cost_per_month`, `pvc_cost_per_month`,
`project_per_month`, `vm_cost_per_month`, and `gpu_cost_per_month` are
NOT in the map. A cost model can contain any `METRIC_CHOICES` metric.

```python
USAGE_METRIC_MAP = {
    "cpu_core_usage_per_hour": "cpu",
    "cpu_core_request_per_hour": "cpu",
    "cpu_core_effective_usage_per_hour": "cpu",
    "memory_gb_usage_per_hour": "memory",
    "memory_gb_request_per_hour": "memory",
    "memory_gb_effective_usage_per_hour": "memory",
    "storage_gb_usage_per_month": "storage",
    "storage_gb_request_per_month": "storage",
    "cluster_core_cost_per_hour": "cpu",
}
```

Missing from map:
- `node_cost_per_month` → should map to `"node"` or `"other"`
- `node_core_cost_per_hour` → `"cpu"` (node-level)
- `node_core_cost_per_month` → `"cpu"` (node-level)
- `cluster_cost_per_month` → `"other"` (cluster-level)
- `cluster_cost_per_hour` → `"other"` (cluster-level)
- `pvc_cost_per_month` → `"storage"` (PVC-level)
- `vm_cost_per_month/hour/core` → `"other"` (VM-level)
- `project_per_month` → `"other"` (project-level, tag-only)
- `gpu_cost_per_month` → `"gpu"`

**Resolution**: `derive_metric_type()` must handle ALL `METRIC_CHOICES`
values. Use a local extended map or heuristic-based derivation (parse
the metric name for keywords: `cpu`/`core` → `"cpu"`,
`mem`/`memory` → `"memory"`, `storage`/`gb`/`pvc` → `"storage"`,
`gpu` → `"gpu"`, else → `"other"`). Tests must cover every
`METRIC_CHOICES` value.

### F9: Write-freeze returns HTTP 400 instead of 503

**Severity**: LOW (semantic, not functional)

**Evidence**: Design doc mentions HTTP 503 Service Unavailable for the
write-freeze. The serializer-level implementation uses
`serializers.ValidationError(...)` which returns HTTP 400 Bad Request.

**Resolution**: Accept HTTP 400 for Phase 1 — the message clearly
states "Cost model writes are temporarily disabled during migration."
HTTP 503 would require a custom DRF exception class. Documented as a
future refinement. Tests assert the error message content, not the
status code (so upgrading to 503 later requires minimal test changes).

### F10: `CostModel.rates` is `JSONField(default=dict)` but stores a list

**Severity**: MEDIUM (type ambiguity in migration and sync)

**Evidence**: Empty cost models: `rates = {}`. Populated cost models:
`rates = [{...}, {...}]`. Migration 0011 handles this with
`.exclude(rates=[]).exclude(rates={})`. The sync code must also handle
`{}` as "no rates".

**Resolution**: `_sync_rate_table()` treats both `{}` and `[]` as
empty. M2 migration follows 0011's exclusion pattern. Tests cover
both empty shapes.

### F11: No coverage threshold enforced in CI

**Severity**: LOW (process, not correctness)

**Evidence**: `.coveragerc` has no `fail_under` setting. `tox.ini`
runs `coverage report` without enforcing a minimum.

**Resolution**: The 80% per-tier target is self-enforced. Each TDD
checkpoint includes a coverage measurement. Final checkpoint asserts
80% across all new code.

### F12: Serializer `update()` calls `update_provider_uuids` before `update()`

**Severity**: INFO (pre-existing, not introduced by Phase 1)

**Evidence**: `CostModelSerializer.update()` calls
`manager.update_provider_uuids(...)` (which queues Celery tasks)
before `manager.update(...)` (which syncs Rate table). These are
separate `@transaction.atomic` methods. A Celery task could
theoretically run between them, seeing stale Rate data.

**Resolution**: Pre-existing behavior, not introduced by Phase 1. The
Celery task reads `CostModel.rates` JSON (not the Rate table yet).
Phase 2 changes the read path. Documented as a known limitation for
Phase 2 migration.

---

## 6. Features to be Tested

### 6.1 Rate Model (TI-1, TI-2)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-1.1 | Create Rate with valid fields | Rate rows persist correctly |
| TC-1.2 | `unique_together` constraint on (price_list, custom_name) | No duplicate rate names per price list |
| TC-1.3 | FK cascade: delete PriceList → deletes Rate rows | Referential integrity |
| TC-1.4 | FK cascade: delete CostModel → PriceListCostModelMap → PriceList → Rate rows | Full cascade chain |
| TC-1.5 | `default_rate` stores Decimal(33,15) precision | Financial accuracy |
| TC-1.6 | `tag_values` stores list of dicts (not dict) | Correct JSON shape |
| TC-1.7 | `metric` field accepts all `METRIC_CHOICES` values | Full metric coverage |
| TC-1.8 | `custom_name` max length 50 enforced | UI constraint |
| TC-1.9 | `related_name="rate_rows"` accessible from PriceList | Reverse relation works |

### 6.2 Helper Functions (TI-4, TI-5, TI-6)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-2.1 | `generate_custom_name` from description | User-friendly label |
| TC-2.2 | `generate_custom_name` from metric.name when no description | Automatic labeling |
| TC-2.3 | `generate_custom_name` deduplication within batch | No `unique_together` violations |
| TC-2.4 | `generate_custom_name` truncation at 50 chars | Max length respected |
| TC-2.5 | `derive_metric_type` for all 20 `METRIC_CHOICES` | Correct classification |
| TC-2.6 | `derive_metric_type` for unknown metric | Graceful fallback |
| TC-2.7 | `extract_default_rate` from tiered rate | Correct Decimal extraction |
| TC-2.8 | `extract_default_rate` from tag rate (default entry) | Tag rate support |
| TC-2.9 | `extract_default_rate` from empty rate | Zero fallback |
| TC-2.10 | `extract_default_rate` Decimal conversion from string | JSON string → Decimal |

### 6.3 Data Migration M2 (TI-3)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-3.1 | CostModel with tiered rates → Rate rows created | Data migrated correctly |
| TC-3.2 | CostModel with tag rates → Rate rows created | Tag rate support |
| TC-3.3 | CostModel with mixed rates → all Rate rows created | Mixed rate types |
| TC-3.4 | CostModel without rates → skipped | No false positives |
| TC-3.5 | CostModel with `rates={}` → skipped | Empty dict handling |
| TC-3.6 | CostModel with `rates=[]` → skipped | Empty list handling |
| TC-3.7 | `custom_name` injected into JSON blobs | Dual-write consistency |
| TC-3.8 | `rate_id` injected into JSON blobs | rate_id round-trip support |
| TC-3.9 | Already-migrated CostModel → skipped | Idempotency |
| TC-3.10 | Reverse migration deletes Rate rows | Clean rollback |
| TC-3.11 | Duplicate metric names get unique custom_names | No constraint violations |
| TC-3.12 | `default_rate` is Decimal, not float | Financial precision |
| TC-3.13 | `select_for_update()` prevents concurrent modification | Race condition safety |

### 6.4 RateSerializer Updates (TI-7)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-4.1 | `rate_id` field accepts valid UUID | API contract |
| TC-4.2 | `rate_id` field allows null | Backward compatibility |
| TC-4.3 | `rate_id` field omitted → no error | Backward compatibility |
| TC-4.4 | `custom_name` field accepts string | API contract |
| TC-4.5 | `custom_name` field omitted → auto-generated | IQ-7 resolution |
| TC-4.6 | `to_representation` includes `rate_id` when present | GET response contract |
| TC-4.7 | `to_representation` omits `rate_id` when absent | Clean legacy output |
| TC-4.8 | `to_representation` includes `custom_name` | GET response contract |
| TC-4.9 | Existing fields (`metric`, `cost_type`, etc.) unchanged | Backward compatibility |
| TC-4.10 | Full serializer round-trip: input → validate → save → output | End-to-end |

### 6.5 Diff-Based `_sync_rate_table()` (TI-8, TI-9)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-5.1 | Create cost model with rates → Rate rows created | Basic sync |
| TC-5.2 | Update: add a new rate → Rate row created | Incremental add |
| TC-5.3 | Update: remove a rate → Rate row deleted | Incremental remove |
| TC-5.4 | Update: modify rate value → Rate row updated, UUID preserved | Diff-based update |
| TC-5.5 | Update: unchanged rates keep UUID | UUID stability |
| TC-5.6 | Backward compat: no `rate_id` → match by `custom_name` | Legacy client support |
| TC-5.7 | Backward compat: rename without `rate_id` → delete + create | Expected degradation |
| TC-5.8 | Invalid `rate_id` (nonexistent) → CostModelException | Ownership validation |
| TC-5.9 | Invalid `rate_id` (belongs to other price_list) → CostModelException | Cross-model protection |
| TC-5.10 | Rename rate + create with old name in same request → succeeds | Delete→update→create ordering |
| TC-5.11 | Metadata-only change (`description`) → no Celery recalculation | Change detection |
| TC-5.12 | Cost-affecting change (`default_rate`) → triggers recalculation | Change detection |
| TC-5.13 | `rate_id` injected into JSON blob after sync | GET response consistency |
| TC-5.14 | `rate_id` injected into PriceList.rates after sync | Dual-write consistency |
| TC-5.15 | Empty rates → all Rate rows deleted | Clear all |
| TC-5.16 | `COST_AFFECTING_FIELDS` classification correct | Optimization correctness |

### 6.6 Unleash Write-Freeze (TI-10, TI-11)

| TC-ID | Description | Business Criterion |
|-------|-------------|-------------------|
| TC-6.1 | `is_cost_model_writes_disabled` returns True when flag enabled | Flag detection |
| TC-6.2 | `is_cost_model_writes_disabled` returns False when flag disabled | Normal operation |
| TC-6.3 | `MockUnleashClient` returns False (on-prem default) | On-prem safety |
| TC-6.4 | `CostModelSerializer.create()` rejects when flag enabled | Write protection |
| TC-6.5 | `CostModelSerializer.update()` rejects when flag enabled | Write protection |
| TC-6.6 | `CostModelSerializer.create()` succeeds when flag disabled | Normal operation |
| TC-6.7 | `CostModelSerializer.update()` succeeds when flag disabled | Normal operation |
| TC-6.8 | No customer context → flag check skipped | Internal calls unblocked |
| TC-6.9 | Error message identifies migration as cause | User clarity |
| TC-6.10 | GET/DELETE requests unaffected by flag | Read/delete not gated |

---

## 7. Features Not to be Tested

| Feature | Rationale |
|---------|-----------|
| `RatesToUsage` model and SQL pipeline | Phase 2 scope |
| `OCPCostUIBreakDownP` table and breakdown API | Phase 4 scope |
| Frontend `rate_id` round-trip | Separate koku-ui PR |
| `CostModelDBAccessor` read-path from Rate table | Phase 1b (read path switch) |
| JSON column drop (`CostModel.rates`, `PriceList.rates`) | Phase 5 scope |
| Celery task execution and recalculation SQL | Pre-existing; mocked in Phase 1 tests |
| RBAC permissions for cost model endpoints | Pre-existing; covered by existing test suite |

---

## 8. Approach

### 8.1 Test-Driven Development (TDD) Cycle

Each implementation phase follows strict Red-Green-Refactor:

1. **TDD Red**: Write failing tests first. Tests define the expected
   behavior from business acceptance criteria. All tests MUST fail
   before implementation begins.
2. **TDD Green**: Write the minimum code to make tests pass. No
   premature optimization.
3. **TDD Refactor**: Improve code quality (extract helpers, reduce
   duplication, add docstrings) while keeping tests green.

### 8.2 Test Tiers

| Tier | Scope | Framework | Target Coverage |
|------|-------|-----------|----------------|
| Unit | Individual functions, model constraints | Django `TestCase` | ≥ 80% of new code |
| Integration | Manager + serializer + model interaction | Django `TestCase` with `IamTestCase` base | ≥ 80% of new code |
| Migration | Schema + data migration correctness | Django `TransactionTestCase` | 100% of migration paths |

### 8.3 Anti-Patterns Avoided

| Anti-Pattern | How Avoided |
|-------------|-------------|
| **Testing implementation details** | Tests assert observable behavior (DB state, API response shape), not internal method calls |
| **Excessive mocking** | Only mock Celery tasks and Unleash client. All DB operations hit the test database. |
| **Test interdependence** | Each test creates its own data in `setUp`. No shared mutable state between tests. |
| **Snapshot/golden-file tests** | Tests assert specific field values, not serialized blobs |
| **Testing Django/DRF internals** | Don't test that `models.UUIDField` generates UUIDs; test that our constraints and business rules work |
| **Ignoring edge cases** | Explicit tests for empty rates, duplicate metrics, max-length strings, Decimal precision |
| **Hard-coded dates/UUIDs** | Use `uuid4()`, `DateHelper()`, `Faker` for dynamic test data |
| **Missing teardown** | `IamTestCase`/`MasuTestCase` handle schema cleanup; `@transaction.atomic` test isolation |

### 8.4 Test Data Strategy

| Data Type | Source | Pattern |
|-----------|--------|---------|
| `Provider` | Pre-seeded OCP provider from `MasuTestCase` | `Provider.objects.filter(type=Provider.PROVIDER_OCP).first()` |
| `CostModel` | Created per test via `CostModelManager().create()` | Patching `update_cost_model_costs` to avoid Celery |
| `PriceList` | Auto-created by `CostModelManager._get_or_create_price_list()` | Verified via `PriceListCostModelMap` |
| `Rate` | Created by `_sync_rate_table()` or `Rate.objects.create()` | Verified via `price_list.rate_rows.all()` |
| Unleash flags | `@patch("masu.processor.is_cost_model_writes_disabled")` | Consistent with existing flag mock pattern |

### 8.5 Mocking Strategy

```python
# Celery task (always mocked — no async execution in tests)
@patch("cost_models.cost_model_manager.update_cost_model_costs")

# Unleash flag (mocked at the helper level, not the client)
@patch("cost_models.serializers.is_cost_model_writes_disabled")

# Provider creation side effects
@patch("masu.celery.tasks.check_report_updates")
```

---

## 9. Item Pass/Fail Criteria

### 9.1 Pass Criteria

- All test cases in all TDD phases pass (`manage.py test cost_models`)
- Coverage ≥ 80% for each new module:
  - `cost_models/models.py` (new Rate class) — ≥ 80%
  - `cost_models/cost_model_manager.py` (new methods) — ≥ 80%
  - `cost_models/serializers.py` (new/modified methods) — ≥ 80%
  - `masu/processor/__init__.py` (new function) — ≥ 80%
- Existing test suite passes without modification (backward compat)
- Migration M2 forward and reverse pass against test database
- No Django `SystemCheckError` from model definitions

### 9.2 Fail Criteria

- Any test case fails
- Coverage < 80% for any new module after refactor phase
- Existing tests fail (regression)
- Migration raises exception during forward or reverse execution

---

## 10. Suspension Criteria and Resumption Requirements

### 10.1 Suspension

- Design doc PR #5980 rejected or requires material changes
- COST-575 migrations (0010, 0011) reverted from main
- Fundamental disagreement on Rate model schema

### 10.2 Resumption

- Design alignment confirmed
- Prerequisite migrations stable on main
- Schema changes agreed upon

---

## 11. Test Deliverables

| Deliverable | Path |
|-------------|------|
| Rate model unit tests | `cost_models/test/test_rate_model.py` |
| Helper function unit tests | `cost_models/test/test_rate_helpers.py` |
| Migration tests | `cost_models/test/test_rate_migration.py` |
| Serializer tests | `cost_models/test/test_serializers.py` (extended) |
| Manager tests | `cost_models/test/test_cost_model_manager.py` (extended) |
| Write-freeze tests | `cost_models/test/test_write_freeze.py` |
| Integration tests | `cost_models/test/test_rate_integration.py` |
| This test plan | `docs/tests/COST-7249/test-plan.md` |
| Due diligence findings | § 5 of this document |
| Coverage report | Generated per checkpoint |

---

## 12. Environmental Needs

- PostgreSQL (test database via `KokuTestRunner`)
- Django test framework (`manage.py test`)
- Coverage tool (`coverage run` + `coverage report`)
- Schema `org1234567` (pre-seeded by `MasuTestCase`)
- Pre-seeded OCP provider (from `ModelBakeryDataLoader`)

---

## 13. TDD Implementation Phases

Each phase follows the Red → Green → Refactor cycle. Checkpoints
between phases perform rigorous due diligence before proceeding.

---

### Phase 1: Rate Model + Migration M1 (DDL)

**Covers**: TI-1, TI-2 | **Test Cases**: TC-1.1 through TC-1.9

#### Phase 1 — TDD Red

Write failing tests that define Rate model behavior:

```
test_rate_model.py:
├── TestRateModel
│   ├── test_create_rate_with_valid_fields             (TC-1.1)
│   ├── test_unique_together_price_list_custom_name    (TC-1.2)
│   ├── test_cascade_delete_price_list_deletes_rates   (TC-1.3)
│   ├── test_cascade_delete_cost_model_chain           (TC-1.4)
│   ├── test_default_rate_decimal_precision             (TC-1.5)
│   ├── test_tag_values_stores_list                     (TC-1.6)
│   ├── test_metric_accepts_all_metric_choices          (TC-1.7)
│   ├── test_custom_name_max_length_enforced            (TC-1.8)
│   └── test_rate_rows_reverse_relation                 (TC-1.9)
```

**Acceptance**: All 9 tests fail with `ImportError` or `DoesNotExist`
(Rate model doesn't exist yet).

#### Phase 1 — TDD Green

Implement:
1. `Rate` class in `cost_models/models.py`
2. Migration `0012_create_rate_table.py`

Key implementation decisions (from due diligence):
- `related_name="rate_rows"` (F1)
- `tag_values = JSONField(default=list)` (F3)
- `db_table = "cost_model_rate"`
- FK to existing `PriceList` (F2)

**Acceptance**: All 9 tests pass. `makemigrations --check` clean.

#### Phase 1 — TDD Refactor

- Add model `__str__` method
- Verify index names don't collide with existing indexes
- Confirm migration is reversible

---

### CHECKPOINT 1: Rate Model Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| Django system checks pass | `manage.py check` | No errors |
| Migration applies cleanly | `manage.py migrate --run-syncdb` | No exceptions |
| Migration reverses cleanly | `manage.py migrate cost_models 0011` | Rate table dropped |
| No `related_name` clash | Inspect `PriceList._meta.related_objects` | `rate_rows` present, no `rates` conflict |
| All `METRIC_CHOICES` accepted | Parameterized test with all 20 values | All pass |
| Coverage ≥ 80% for Rate model | `coverage report --include="*/models.py"` | ≥ 80% of new lines |

---

### Phase 2: Helper Functions

**Covers**: TI-4, TI-5, TI-6 | **Test Cases**: TC-2.1 through TC-2.10

#### Phase 2 — TDD Red

Write failing tests for all three helper functions:

```
test_rate_helpers.py:
├── TestGenerateCustomName
│   ├── test_from_description                           (TC-2.1)
│   ├── test_from_metric_name_when_no_description       (TC-2.2)
│   ├── test_deduplication_within_batch                  (TC-2.3)
│   └── test_truncation_at_50_chars                      (TC-2.4)
├── TestDeriveMetricType
│   ├── test_all_metric_choices_mapped                   (TC-2.5)
│   └── test_unknown_metric_returns_other                (TC-2.6)
├── TestExtractDefaultRate
│   ├── test_from_tiered_rate                            (TC-2.7)
│   ├── test_from_tag_rate_default_entry                 (TC-2.8)
│   ├── test_from_empty_rate                             (TC-2.9)
│   └── test_decimal_conversion_from_string              (TC-2.10)
```

**Acceptance**: All 10 tests fail with `ImportError` (functions don't
exist yet).

#### Phase 2 — TDD Green

Implement in `cost_models/cost_model_manager.py` (or a new
`cost_models/rate_helpers.py` if cleaner):

- `generate_custom_name(rate_data, existing_names=None) → str`
- `derive_metric_type(metric_name) → str`
- `extract_default_rate(rate_data) → Decimal`

Key implementation decisions (from due diligence):
- `derive_metric_type` uses heuristic for metrics not in
  `USAGE_METRIC_MAP` (F8): parse metric name for `cpu`/`core` →
  `"cpu"`, `mem` → `"memory"`, `storage`/`pvc` → `"storage"`,
  `gpu` → `"gpu"`, else → `"other"`
- `extract_default_rate` checks tag_values default entry (F4)
- `generate_custom_name` appends ` (N)` suffix for duplicates

**Acceptance**: All 10 tests pass.

#### Phase 2 — TDD Refactor

- Ensure `derive_metric_type` is deterministic and documented
- Add type hints to all three functions
- Extract metric parsing into a testable constant/map

---

### CHECKPOINT 2: Helper Functions Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| All 20 `METRIC_CHOICES` mapped | `test_all_metric_choices_mapped` | All return non-empty string |
| `extract_default_rate` returns Decimal | Type assertion in tests | `isinstance(result, Decimal)` |
| `generate_custom_name` idempotent | Same input → same output | Deterministic |
| No import cycle | `python -c "from cost_models.cost_model_manager import generate_custom_name"` | No error |
| Coverage ≥ 80% for helpers | `coverage report` | ≥ 80% of new lines |

---

### Phase 3: Data Migration M2

**Covers**: TI-3 | **Test Cases**: TC-3.1 through TC-3.13

#### Phase 3 — TDD Red

Write failing tests for the data migration:

```
test_rate_migration.py:
├── TestMigrateJsonToRateRows
│   ├── test_tiered_rates_migrated                      (TC-3.1)
│   ├── test_tag_rates_migrated                         (TC-3.2)
│   ├── test_mixed_rates_migrated                       (TC-3.3)
│   ├── test_no_rates_skipped                           (TC-3.4)
│   ├── test_empty_dict_rates_skipped                   (TC-3.5)
│   ├── test_empty_list_rates_skipped                   (TC-3.6)
│   ├── test_custom_name_injected_into_json             (TC-3.7)
│   ├── test_rate_id_injected_into_json                 (TC-3.8)
│   ├── test_already_migrated_skipped                   (TC-3.9)
│   ├── test_reverse_migration_deletes_rates            (TC-3.10)
│   ├── test_duplicate_metric_unique_custom_names       (TC-3.11)
│   ├── test_default_rate_is_decimal                    (TC-3.12)
│   └── test_select_for_update_locking                  (TC-3.13)
```

**Acceptance**: All 13 tests fail (migration doesn't exist yet).

#### Phase 3 — TDD Green

Implement migration `0013_migrate_json_to_rate_rows.py`:

- `RunPython` with `atomic=False` on the migration class
- Per-mapping `transaction.atomic()` + `select_for_update()`
- `bulk_create` Rate rows per mapping (F5)
- Inject `custom_name` and `rate_id` back into JSON blobs
- Skip mappings where Rate rows already exist (idempotency)
- `tag_values` defaults to `[]` not `{}` (F3)
- `default_rate` extracted from tag default entry (F4)
- Decimal conversion via `Decimal(str(value))` (TC-3.12)
- Reverse function deletes Rate rows

**Acceptance**: All 13 tests pass.

#### Phase 3 — TDD Refactor

- Extract migration helper functions (testable outside migration)
- Ensure reverse migration is safe (doesn't delete manually-created
  Rate rows — scope deletion to auto-migrated ones)
- Performance: verify `bulk_create` batch size

---

### CHECKPOINT 3: Data Migration Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| Forward migration succeeds | `manage.py migrate cost_models` | No exceptions |
| Reverse migration succeeds | `manage.py migrate cost_models 0012` | Rate rows removed |
| Forward then reverse then forward | Triple-apply test | Idempotent |
| JSON blobs updated with custom_name | Query `CostModel.rates` after migration | All entries have `custom_name` |
| JSON blobs updated with rate_id | Query `CostModel.rates` after migration | All entries have `rate_id` (UUID string) |
| Rate count matches JSON rate count | `Rate.objects.count()` vs `sum(len(cm.rates) for cm)` | Equal |
| No `unique_together` violations | Migration completes without `IntegrityError` | Clean |
| Coverage ≥ 80% for migration | `coverage report` | ≥ 80% of migration code |

---

### Phase 4: RateSerializer Updates

**Covers**: TI-7 | **Test Cases**: TC-4.1 through TC-4.10

#### Phase 4 — TDD Red

Extend `test_serializers.py` with new test methods:

```
test_serializers.py (extended):
├── CostModelSerializerTest
│   ├── test_rate_id_field_accepts_uuid                 (TC-4.1)
│   ├── test_rate_id_field_allows_null                  (TC-4.2)
│   ├── test_rate_id_field_omitted_no_error             (TC-4.3)
│   ├── test_custom_name_field_accepts_string           (TC-4.4)
│   ├── test_custom_name_field_omitted_auto_generated   (TC-4.5)
│   ├── test_to_representation_includes_rate_id         (TC-4.6)
│   ├── test_to_representation_omits_rate_id_if_absent  (TC-4.7)
│   ├── test_to_representation_includes_custom_name     (TC-4.8)
│   ├── test_existing_fields_unchanged                  (TC-4.9)
│   └── test_serializer_round_trip                      (TC-4.10)
```

**Acceptance**: Tests for `rate_id` and `custom_name` fail (fields
don't exist on `RateSerializer` yet). Tests for existing fields pass.

#### Phase 4 — TDD Green

Modify `cost_models/serializers.py`:

- Add `rate_id = serializers.UUIDField(required=False, allow_null=True)`
  to `RateSerializer`
- Add `custom_name = serializers.CharField(max_length=50, required=False,
  allow_blank=True)` to `RateSerializer`
- Update `to_representation()` to include `rate_id` and `custom_name`
  when present in the rate dict
- Ensure `to_internal_value()` preserves `rate_id` and `custom_name`

**Acceptance**: All 10 tests pass. Existing serializer tests still pass.

#### Phase 4 — TDD Refactor

- Consolidate `to_representation` logic
- Ensure `rate_id` is UUID-formatted in output (not raw string)
- Add validation: `custom_name` max 50 chars

---

### CHECKPOINT 4: RateSerializer Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| All existing serializer tests pass | `manage.py test cost_models.test.test_serializers` | 0 failures |
| `rate_id` absent from legacy GET response | Test with pre-existing CostModel | No `rate_id` key |
| `rate_id` present in new GET response | Test after `_sync_rate_table` | UUID string |
| `custom_name` appears in GET response | Test after create/update | Non-empty string |
| `to_internal_value` preserves extra fields | Test with `rate_id` + `custom_name` in input | Both survive |
| Coverage ≥ 80% for serializer changes | `coverage report` | ≥ 80% of modified lines |

---

### Phase 5: Diff-Based `_sync_rate_table()`

**Covers**: TI-8, TI-9 | **Test Cases**: TC-5.1 through TC-5.16

#### Phase 5 — TDD Red

Extend `test_cost_model_manager.py` with new test methods:

```
test_cost_model_manager.py (extended):
├── CostModelManagerTest
│   ├── test_create_with_rates_creates_rate_rows        (TC-5.1)
│   ├── test_update_add_rate_creates_row                (TC-5.2)
│   ├── test_update_remove_rate_deletes_row             (TC-5.3)
│   ├── test_update_modify_rate_preserves_uuid          (TC-5.4)
│   ├── test_update_unchanged_rate_keeps_uuid           (TC-5.5)
│   ├── test_no_rate_id_matches_by_custom_name          (TC-5.6)
│   ├── test_rename_without_rate_id_is_delete_create    (TC-5.7)
│   ├── test_invalid_rate_id_raises_exception           (TC-5.8)
│   ├── test_foreign_rate_id_raises_exception           (TC-5.9)
│   ├── test_rename_and_create_old_name_succeeds        (TC-5.10)
│   ├── test_description_change_no_recalculation        (TC-5.11)
│   ├── test_default_rate_change_triggers_recalc        (TC-5.12)
│   ├── test_rate_id_injected_into_model_json           (TC-5.13)
│   ├── test_rate_id_injected_into_price_list_json      (TC-5.14)
│   ├── test_empty_rates_deletes_all_rows               (TC-5.15)
│   └── test_cost_affecting_fields_classification       (TC-5.16)
```

**Acceptance**: All 16 tests fail (`_sync_rate_table` doesn't exist).

#### Phase 5 — TDD Green

Implement in `cost_models/cost_model_manager.py`:

- `_sync_rate_table(self, price_list, rates_data)`
- `_apply_rate_fields(self, rate_obj, rate_data) → bool`
- `_rate_fields_from_data(rate_data) → dict`
- `COST_AFFECTING_FIELDS` class constant
- Modify `create()` to call `_sync_rate_table()`
- Modify `update()` to call `_sync_rate_table()` and remove
  redundant PriceList save (F7)

Key implementation decisions:
- Delete → update → create ordering (Gap E)
- `custom_name` backward-compat matching (Gap B)
- `rate_id` ownership validation against `existing` dict (Gap D)
- `rate_id` injection into JSON blobs

**Acceptance**: All 16 tests pass. All existing manager tests pass.

#### Phase 5 — TDD Refactor

- Extract `COST_AFFECTING_FIELDS` to module level for reuse
- Add logging for rate create/update/delete operations
- Profile: ensure single-digit queries per sync call (no N+1)

---

### CHECKPOINT 5: Sync Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| All existing manager tests pass | `manage.py test cost_models.test.test_cost_model_manager` | 0 failures |
| UUID stability verified | Create, update unrelated field, check UUID | Same UUID |
| Backward compat verified | Update without `rate_id` → match by name | UUID preserved for unchanged rates |
| Operation ordering verified | Rename A→B + create A in same request | No `IntegrityError` |
| JSON blobs contain `rate_id` after create | Query `CostModel.rates` | Each entry has `rate_id` |
| JSON blobs contain `rate_id` after update | Query `CostModel.rates` | Each entry has `rate_id` |
| No N+1 queries | `assertNumQueries` or query logging | Bounded query count |
| Coverage ≥ 80% for sync methods | `coverage report` | ≥ 80% of new lines |

---

### Phase 6: Unleash Write-Freeze

**Covers**: TI-10, TI-11 | **Test Cases**: TC-6.1 through TC-6.10

#### Phase 6 — TDD Red

Write tests in a new file:

```
test_write_freeze.py:
├── TestIsWriteDisabled
│   ├── test_returns_true_when_flag_enabled             (TC-6.1)
│   ├── test_returns_false_when_flag_disabled           (TC-6.2)
│   └── test_mock_client_returns_false                  (TC-6.3)
├── TestWriteFreezeGating
│   ├── test_create_rejected_when_disabled              (TC-6.4)
│   ├── test_update_rejected_when_disabled              (TC-6.5)
│   ├── test_create_succeeds_when_enabled               (TC-6.6)
│   ├── test_update_succeeds_when_enabled               (TC-6.7)
│   ├── test_no_customer_skips_check                    (TC-6.8)
│   ├── test_error_message_content                      (TC-6.9)
│   └── test_get_delete_unaffected                      (TC-6.10)
```

**Acceptance**: All 10 tests fail.

#### Phase 6 — TDD Green

Implement:

1. In `masu/processor/__init__.py`:
   - `COST_MODEL_WRITE_FREEZE_FLAG = "cost-management.backend.disable-cost-model-writes"`
   - `is_cost_model_writes_disabled(schema) → bool`

2. In `cost_models/serializers.py`:
   - Import `is_cost_model_writes_disabled`
   - Add gate at top of `create()` and `update()`:
     ```python
     schema = self.customer.schema_name if self.customer else None
     if schema and is_cost_model_writes_disabled(schema):
         raise serializers.ValidationError(
             error_obj("cost-models", "Cost model writes are temporarily disabled during migration.")
         )
     ```

**Acceptance**: All 10 tests pass.

#### Phase 6 — TDD Refactor

- Extract gate logic into private method `_check_write_freeze()`
- Add `# pragma: no cover` to `is_cost_model_writes_disabled` (matches
  existing pattern for Unleash helpers)
- Verify `LOG.info` message in gate function

---

### CHECKPOINT 6: Write-Freeze Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| Flag constant follows naming convention | Grep for `cost-management.backend.` prefix | Consistent |
| `MockUnleashClient` returns False | Unit test (TC-6.3) | On-prem safe |
| Serializer gate uses `self.customer` | Code review | Not `data.get("schema")` |
| GET/DELETE unaffected | View-level test (TC-6.10) | 200 OK |
| Error message is actionable | Assertion on message string | Contains "migration" |
| Coverage ≥ 80% for write-freeze code | `coverage report` | ≥ 80% |

---

### Phase 7: Integration Tests

**Covers**: TI-12, TI-13 | **Test Cases**: Full end-to-end

#### Phase 7 — TDD Red

Write integration tests that exercise the full stack:

```
test_rate_integration.py:
├── TestRateIntegration
│   ├── test_create_cost_model_with_rates_full_round_trip
│   │   → Creates cost model via serializer
│   │   → Verifies Rate rows exist
│   │   → Verifies GET response includes rate_id + custom_name
│   │   → Verifies JSON blobs consistent with Rate table
│   │
│   ├── test_update_cost_model_rates_diff_sync
│   │   → Creates cost model with 3 rates
│   │   → Updates: modify 1, remove 1, add 1
│   │   → Verifies Rate row UUIDs: 1 preserved, 1 deleted, 1 new
│   │   → Verifies GET response reflects changes
│   │
│   ├── test_update_then_get_rate_id_stability
│   │   → Creates cost model
│   │   → GET → captures rate_ids
│   │   → PUT with same rates (including rate_ids)
│   │   → GET → rate_ids unchanged
│   │
│   ├── test_write_freeze_blocks_create_and_update
│   │   → Enable flag mock
│   │   → POST cost model → 400 with message
│   │   → PUT cost model → 400 with message
│   │   → GET cost model → 200 (unaffected)
│   │
│   ├── test_backward_compat_no_rate_id_in_payload
│   │   → Creates cost model (rates get rate_ids)
│   │   → PUT with same rates but WITHOUT rate_ids
│   │   → Verifies rates matched by custom_name
│   │   → Verifies UUIDs preserved for unchanged rates
│   │
│   └── test_migration_then_api_update_consistency
│       → Runs M2 migration on test data
│       → Updates cost model via API
│       → Verifies Rate table, JSON blobs, and API response all consistent
```

**Acceptance**: All integration tests fail initially (components not
wired together yet — depends on Phase 5 completion).

#### Phase 7 — TDD Green

Wire all components together. The integration tests should pass once
Phases 1-6 are complete and properly integrated.

**Acceptance**: All integration tests pass. Full existing test suite
passes.

#### Phase 7 — TDD Refactor

- Consolidate shared test setup into helper methods
- Profile query counts for integration scenarios
- Run full coverage report

---

### CHECKPOINT 7: Final Due Diligence

| Check | Method | Pass Criterion |
|-------|--------|---------------|
| Full test suite passes | `manage.py test` | 0 failures |
| Coverage ≥ 80% per tier | `coverage report` per new file | All ≥ 80% |
| No migration conflicts | `makemigrations --check` | Clean |
| Backward compatibility | Existing API tests unchanged | 0 regressions |
| JSON blob + Rate table consistency | Integration test | Matching data |
| `rate_id` round-trip: create → GET → PUT → GET | Integration test | UUID stable |
| Write-freeze blocks writes only | View test with flag on/off | Create/update blocked, GET/DELETE pass |
| On-prem safety (MockUnleashClient) | Unit test | Flag returns False |
| No Django system check errors | `manage.py check` | 0 errors |
| Performance: query count per create/update | `assertNumQueries` | Bounded, no N+1 |

---

## 14. Schedule

| Phase | Estimated Duration | Dependencies |
|-------|-------------------|-------------|
| Phase 1: Rate Model + M1 | 0.5 day | Design PR merged or aligned |
| Phase 2: Helper Functions | 0.5 day | Phase 1 |
| Phase 3: Data Migration M2 | 1 day | Phase 1, Phase 2 |
| Phase 4: RateSerializer | 0.5 day | Phase 1 |
| Phase 5: `_sync_rate_table()` | 1.5 days | Phase 1, Phase 2, Phase 4 |
| Phase 6: Write-Freeze | 0.5 day | None (independent) |
| Phase 7: Integration Tests | 1 day | All phases |
| **Total** | **~5.5 days** | |

---

## 15. Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-06 | Initial test plan. 13 test items, 68 test cases across 7 TDD phases with 7 checkpoints. 12 due diligence findings documented and addressed. |
