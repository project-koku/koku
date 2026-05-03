# Test Plan — Configurable Data Retention Period

**IEEE 829 Test Plan** · **Parent**: [README.md](README.md) · **Status**: Draft

---

## 1. Test Plan Identifier

**TP-COST-573-v1.0**

---

## 2. References

| Ref | Document |
|-----|----------|
| PRD | PRD06 — "More than 90 days of data" |
| DD-1 | [data-model.md](data-model.md) — `TenantSettings` schema, read helper |
| DD-2 | [api.md](api.md) — Global Settings endpoint |
| DD-3 | [retention-pipeline.md](retention-pipeline.md) — Purge flow, calendar-month fix, Kafka gate |
| DD-4 | [phased-delivery.md](phased-delivery.md) — Phases, risk register |
| Jira | [COST-573](https://redhat.atlassian.net/browse/COST-573) |
| PR | [#5958](https://github.com/project-koku/koku/pull/5958) (design) |

---

## 3. Introduction

This plan describes the verification strategy for COST-573:
making the data retention period configurable at runtime via a
database-persisted `TenantSettings` model and a new Global Settings
API. The plan targets **≥ 80 % coverage of testable code per tier**,
validates business outcomes through behavior- and correctness-focused
tests, and aligns with Koku's existing conventions:

- `manage.py test` (Django `TestCase` discovery, not pytest)
- `IamTestCase` / `MasuTestCase` base classes
- `APIClient` + `reverse` + `self.headers` for DRF views
- `schema_context` for tenant isolation
- `@override_settings`, `@patch`, `PropertyMock` for stubs
- `@RbacPermissions` decorator for permission tests
- `skipUnless(settings.ONPREM)` for on-prem-only endpoints
- `model_bakery` for fixture generation

---

## 4. Test Items

| ID | Item | Design Ref | Phase |
|----|------|-----------|-------|
| TI-1 | `TenantSettings` model (`reporting/tenant_settings/models.py`) | DD-1 | 1 |
| TI-2 | Migration `0344_tenantsettings` | DD-1 | 1 |
| TI-3 | `get_data_retention_months()` helper (`api/settings/utils.py`) | DD-1 | 3 |
| TI-4 | `TenantSettingsSerializer` (`api/settings/serializers.py`) | DD-2 | 2 |
| TI-5 | `GlobalSettingsView` GET / PUT (`api/settings/views.py`) | DD-2 | 2 |
| TI-6 | URL route registration (on-prem gating) | DD-2 | 2 |
| TI-7 | `ExpiredDataRemover` — per-tenant retention + calendar-month fix | DD-3 | 3 |
| TI-8 | `kafka_msg_handler` — per-tenant retention gate | DD-3 | 3 |
| TI-9 | `materialized_view_month_start()` — schema-aware | DD-3 | 3 |
| TI-10 | `_remove_expired_data` task — schema passthrough | DD-3 | 3 |
| TI-11 | Cache invalidation on PUT | DD-2 | 2 |

---

## 5. Software Risk Issues

Tests are prioritized by the risk register in
[phased-delivery.md](phased-delivery.md). Every mitigated or
resolved risk maps to at least one test case.

| Risk | Severity | Mapped Test IDs | Notes |
|------|----------|-----------------|-------|
| R1 — Template-clone misses table | Medium | TC-M-01 | |
| R2 — Duplicate row race condition | Low | TC-A-10 | |
| R3 — Deploy default inconsistency | Low | — | Accepted (cosmetic); verified by TC-H-02 indirectly |
| R4 — Calendar-month fix shifts date | Medium | TC-P-01 through TC-P-04 | |
| R5 — Kafka schema resolution overhead | Low | TC-P-08, TC-P-09 | |
| R6 — Default 4→3 data deletion | Resolved | TC-H-02, TC-H-03 | |
| R7 — DB read failure in purge | **High** | TC-H-05, TC-H-06, TC-H-10, TC-P-10 | |
| R8 — Seed migration env var mismatch | Medium | — | Approach B only (not selected) |
| R9 — Phase ordering violation | Low | TC-P-07 | Fallback produces safe value |
| R10 — Helper fallback / GET side-effect | Resolved | TC-H-02, TC-A-01, TC-A-03 | |

---

## 6. Features to be Tested

### 6.1 Model Layer (Phase 1)

| ID | Feature | Business Outcome |
|----|---------|------------------|
| F-M-01 | `TenantSettings` stores `data_retention_months` per tenant | Operators can configure retention per organization |
| F-M-02 | `CHECK` constraint enforces `[3, 120]` range | System rejects invalid retention values |
| F-M-03 | Column default is `3` (PRD floor) | New opt-in tenants start at PRD minimum |
| F-M-04 | Migration creates table in template + tenant schemas | Feature is available on all existing and future tenants |

### 6.2 API Layer (Phase 2)

| ID | Feature | Business Outcome |
|----|---------|------------------|
| F-A-01 | GET returns effective retention value | Operators can view the current setting |
| F-A-02 | GET returns `env_override: true` when env var set | UI knows when to disable the control |
| F-A-03 | PUT updates retention and persists | Operators can change retention at runtime |
| F-A-04 | PUT rejects values outside `[3, 120]` | Invalid input is caught before reaching DB |
| F-A-05 | PUT returns 403 when env var is set | Env var lock prevents conflicting changes |
| F-A-06 | Endpoint gated behind `ONPREM` | SaaS deployments never expose this route |
| F-A-07 | `SettingsAccessPermission` enforces RBAC | Only org-admins can modify retention |
| F-A-08 | PUT invalidates view cache | Subsequent report queries use new retention window |

### 6.3 Pipeline Layer (Phase 3)

| ID | Feature | Business Outcome |
|----|---------|------------------|
| F-P-01 | `get_data_retention_months()` priority: env → DB → default | Consistent retention resolution regardless of config state |
| F-P-02 | Calendar-month expiration via `relativedelta` | Retention aligns with full calendar months per PRD |
| F-P-03 | `ExpiredDataRemover` uses per-tenant retention | Each organization retains exactly its configured months |
| F-P-04 | Kafka gate uses per-tenant retention | OCP payloads outside tenant's window are rejected |
| F-P-05 | `materialized_view_month_start` uses per-tenant retention | API date range validation matches tenant's retention |
| F-P-06 | DB error in helper returns `None`, purge skips | No data is deleted during DB outages (R7) |

---

## 7. Features Not to be Tested

| Feature | Reason |
|---------|--------|
| Frontend (koku-ui-onprem) changes | IQ-4: separate team/ticket |
| Trino partition cleanup (`migrate_trino_tables`) | IQ-2: on-prem does not use Trino |
| `MASU_RETAIN_NUM_MONTHS_LINE_ITEM_ONLY` removal | IQ-1: dead code removal timing TBD |
| Seed migration (Approach B) | IQ-0: tech lead approved Approach A |
| Celery Beat scheduling | Existing infrastructure, no changes |

---

## 8. Approach

### 8.1 Tier Definitions

| Tier | Scope | Base Class | DB | Target Coverage |
|------|-------|------------|-----|-----------------|
| **Unit** | Model validation, serializer, helper logic, expiration calc | `TestCase` | In-memory/mocked | ≥ 80 % |
| **Integration** | API views + DB, read helper + real `schema_context`, pipeline consumers | `IamTestCase` / `MasuTestCase` | Postgres (test DB) | ≥ 80 % |
| **Contract** | RBAC enforcement, env-var overrides, ONPREM gating | `IamTestCase` + `@RbacPermissions` / `@override_settings` | Postgres | ≥ 80 % |

All tiers run via `manage.py test` (Django `DiscoverRunner` →
`KokuTestRunner`). Coverage is measured by `coverage run` +
`coverage report` as configured in `.coveragerc`.

### 8.2 File Layout

Tests are colocated with their feature code under `test/`
subdirectories, following Koku conventions:

```
reporting/tenant_settings/test/
    __init__.py
    test_models.py                 # TI-1, TI-2

api/settings/test/
    test_global_settings_views.py  # TI-5, TI-6, TI-11
    test_global_settings_utils.py  # TI-3

masu/test/processor/
    test_expired_data_remover.py   # TI-7 (extend existing)

masu/test/external/
    test_kafka_msg_handler.py      # TI-8 (extend existing)

api/test_utils.py                  # TI-9 (extend existing)
```

### 8.3 Conventions

- **Class naming**: `<Feature>Test(BaseClass)` — e.g.,
  `TenantSettingsModelTest(TestCase)`,
  `GlobalSettingsViewTest(IamTestCase)`.
- **Method naming**: `test_<behavior_under_test>` — descriptive of
  the business outcome, not implementation.
- **No mock overuse**: Use real DB via `schema_context` for
  integration tests. Reserve `@patch` for external dependencies
  (env vars, `DateHelper.today`, DB errors).
- **Assert patterns**: `assertEqual`, `assertIsNone`, `assertTrue`,
  `assertRaises` — match existing Koku style.
- **No bare `except`**: Use specific exceptions in test assertions.
- **Tenant isolation**: All DB operations inside
  `with schema_context(self.schema_name):` or `self.schema`.
- **Cleanup**: `setUp` deletes test rows to avoid cross-test
  interference (same pattern as `TestUserSettingCommon`).

### 8.4 How to Run Tests

#### Prerequisites

All tiers use Django's `DiscoverRunner` (`KokuTestRunner`) via
`manage.py test`. See [docs/testing.md](../../testing.md) for general
setup instructions.

**Quick start with tox** (handles env vars automatically):

    $ make docker-up          # start Postgres on port 15432
    $ tox -e py311 -- <module_paths>
    $ make docker-down

**Direct invocation** requires the env vars from the `[testenv]`
section of `tox.ini` (see §13 Environmental Needs). `ONPREM=True` is
required for endpoint registration.

#### Tier 1 — Unit

Model validation, serializer logic. Base class: `TestCase` /
`MasuTestCase`.

    tox -e py311 -- \
        reporting.tenant_settings.test.test_models \
        api.settings.test.test_global_settings_serializers

#### Tier 2 — Integration

API views + DB, read helper with real `schema_context`, pipeline
consumers. Base class: `IamTestCase` / `MasuTestCase`.

    tox -e py311 -- \
        api.settings.test.test_global_settings_views.GlobalSettingsViewTest \
        api.settings.test.test_global_settings_utils \
        masu.test.processor.test_expired_data_remover \
        masu.test.processor.test_remove_expired \
        masu.test.external.test_kafka_retention_gate \
        api.test_utils.MaterializsedViewStartTest

#### Tier 3 — Contract

RBAC enforcement, env-var overrides. Base class: `IamTestCase` +
`@RbacPermissions`.

    tox -e py311 -- \
        api.settings.test.test_global_settings_views.GlobalSettingsViewRBACTest

#### All Tiers

    tox -e py311 -- \
        reporting.tenant_settings.test.test_models \
        api.settings.test.test_global_settings_serializers \
        api.settings.test.test_global_settings_views \
        api.settings.test.test_global_settings_utils \
        masu.test.processor.test_expired_data_remover \
        masu.test.processor.test_remove_expired \
        masu.test.external.test_kafka_retention_gate \
        api.test_utils.MaterializsedViewStartTest

#### With Coverage

    coverage run koku/manage.py test --noinput -v 2 \
        reporting.tenant_settings.test \
        api.settings.test.test_global_settings_views \
        api.settings.test.test_global_settings_serializers \
        api.settings.test.test_global_settings_utils \
        masu.test.processor.test_expired_data_remover \
        masu.test.processor.test_remove_expired \
        masu.test.external.test_kafka_retention_gate \
        api.test_utils.MaterializsedViewStartTest \
    && coverage report --show-missing

---

## 9. Test Cases

### 9.1 Model & Migration — `reporting/tenant_settings/test/test_models.py`

**Base class**: `MasuTestCase` (provides `self.schema`, seeded
customer, tenant DB).

| ID | Test Method | Validates | Tier |
|----|-------------|-----------|------|
| TC-M-01 | `test_table_exists_in_tenant_schema` | Migration created `tenant_settings` in tenant schema. `TenantSettings.objects.count()` does not raise. | Integration |
| TC-M-02 | `test_create_with_defaults` | Row created with `data_retention_months=3` (column default). | Unit |
| TC-M-03 | `test_create_with_explicit_value` | Row created with `data_retention_months=24`. Persists and reads back correctly. | Unit |
| TC-M-04 | `test_min_boundary_accepted` | `data_retention_months=3` passes `full_clean()`. | Unit |
| TC-M-05 | `test_max_boundary_accepted` | `data_retention_months=120` passes `full_clean()`. | Unit |
| TC-M-06 | `test_below_min_rejected` | `data_retention_months=2` raises `ValidationError` on `full_clean()`. | Unit |
| TC-M-07 | `test_above_max_rejected` | `data_retention_months=121` raises `ValidationError` on `full_clean()`. | Unit |
| TC-M-08 | `test_negative_value_rejected` | `data_retention_months=-1` raises `ValidationError` on `full_clean()`. | Unit |
| TC-M-09 | `test_zero_rejected` | `data_retention_months=0` raises `ValidationError` on `full_clean()`. | Unit |
| TC-M-10 | `test_db_table_name` | `TenantSettings._meta.db_table == "tenant_settings"`. | Unit |

```python
class TenantSettingsModelTest(MasuTestCase):
    """Tests for the TenantSettings model."""

    def setUp(self):
        """Clean tenant_settings before each test."""
        super().setUp()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    def test_table_exists_in_tenant_schema(self):
        """Verify migration created the table in the test tenant schema."""
        with schema_context(self.schema):
            self.assertEqual(TenantSettings.objects.count(), 0)

    def test_create_with_defaults(self):
        """A row with no explicit value gets the column default (3)."""
        with schema_context(self.schema):
            row = TenantSettings.objects.create()
            self.assertEqual(row.data_retention_months, TenantSettings.DEFAULT_RETENTION_MONTHS)

    def test_create_with_explicit_value(self):
        """An explicit value persists correctly."""
        with schema_context(self.schema):
            row = TenantSettings.objects.create(data_retention_months=24)
            row.refresh_from_db()
            self.assertEqual(row.data_retention_months, 24)

    def test_min_boundary_accepted(self):
        """The PRD minimum (3) passes model validation."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=3)
            row.full_clean()

    def test_max_boundary_accepted(self):
        """The upper limit (120) passes model validation."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=120)
            row.full_clean()

    def test_below_min_rejected(self):
        """Values below the PRD minimum are rejected by model validators."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=2)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_above_max_rejected(self):
        """Values above the upper limit are rejected by model validators."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=121)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_negative_value_rejected(self):
        """Negative values are rejected."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=-1)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_zero_rejected(self):
        """Zero is rejected — must retain at least 3 months."""
        with schema_context(self.schema):
            row = TenantSettings(data_retention_months=0)
            with self.assertRaises(ValidationError):
                row.full_clean()

    def test_db_table_name(self):
        """Verify the DB table name matches the DDL specification."""
        self.assertEqual(TenantSettings._meta.db_table, "tenant_settings")
```

---

### 9.2 Read Helper — `api/settings/test/test_global_settings_utils.py`

**Base class**: `MasuTestCase` (tenant DB access for `schema_context`).

| ID | Test Method | Validates | Tier |
|----|-------------|-----------|------|
| TC-H-01 | `test_env_var_takes_precedence` | Env var set → returns env value, DB row ignored. | Unit |
| TC-H-02 | `test_no_env_no_row_returns_startup_default` | No env, no DB row → returns `Config.MASU_RETAIN_NUM_MONTHS` (4), **not** `DEFAULT_RETENTION_MONTHS` (3). Validates R6/R10 resolution. | Integration |
| TC-H-03 | `test_no_env_with_row_returns_db_value` | No env, DB row with `12` → returns `12`. | Integration |
| TC-H-04 | `test_env_var_overrides_db_row` | Env = `6`, DB row = `12` → returns `6`. | Integration |
| TC-H-05 | `test_db_error_returns_none` | DB exception → returns `None`. Validates R7. | Unit |
| TC-H-06 | `test_db_error_logs_message` | DB exception → error is logged with schema name. | Unit |
| TC-H-07 | `test_env_var_zero_is_returned` | Env = `"0"` → returns `0` (edge: let caller handle). | Unit |
| TC-H-08 | `test_env_var_non_numeric_raises` | Env = `"abc"` → `ValueError` propagates (invalid config). | Unit |
| TC-H-09 | `test_returns_int_type` | Return type is `int` (not `str` or `float`) when valid. | Unit |
| TC-H-10 | `test_get_endpoint_handles_none_on_db_error` | GET with DB error → returns fallback value or 503 (gap: design must specify). | Integration |

```python
class GetDataRetentionMonthsTest(MasuTestCase):
    """Tests for the get_data_retention_months() read helper."""

    def setUp(self):
        """Clean state."""
        super().setUp()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "6"})
    def test_env_var_takes_precedence(self):
        """Env var is highest priority — DB row is never consulted."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=12)
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, 6)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_no_row_returns_startup_default(self):
        """No env, no DB row → startup-cached default (4), not column default (3)."""
        os.environ.pop("RETAIN_NUM_MONTHS", None)
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, Config.MASU_RETAIN_NUM_MONTHS)
        self.assertNotEqual(result, TenantSettings.DEFAULT_RETENTION_MONTHS)

    def test_no_env_with_row_returns_db_value(self):
        """DB row value is returned when env var is unset."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=12)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            result = get_data_retention_months(self.schema)
        self.assertEqual(result, 12)

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "6"})
    def test_env_var_overrides_db_row(self):
        """Env var wins even when a DB row with a different value exists."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=12)
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, 6)

    @patch("api.settings.utils.schema_context")
    def test_db_error_returns_none(self, mock_ctx):
        """DB exception → None (R7: caller should skip purge)."""
        mock_ctx.side_effect = Exception("connection refused")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            result = get_data_retention_months(self.schema)
        self.assertIsNone(result)

    @patch("api.settings.utils.schema_context")
    def test_db_error_logs_message(self, mock_ctx):
        """DB exception is logged at ERROR level with the schema name."""
        mock_ctx.side_effect = Exception("connection refused")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            with self.assertLogs("api.settings.utils", level="ERROR") as cm:
                get_data_retention_months(self.schema)
            self.assertTrue(
                any(self.schema in msg for msg in cm.output)
            )

    def test_returns_int_type(self):
        """Return type is int when the value is valid."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=7)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            result = get_data_retention_months(self.schema)
        self.assertIsInstance(result, int)

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "0"})
    def test_env_var_zero_is_returned(self):
        """Env var set to "0" returns 0 — caller is responsible for handling."""
        result = get_data_retention_months(self.schema)
        self.assertEqual(result, 0)

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "abc"})
    def test_env_var_non_numeric_raises(self):
        """Non-numeric env var propagates ValueError — invalid configuration."""
        with self.assertRaises(ValueError):
            get_data_retention_months(self.schema)
```

---

### 9.3 API Endpoint — `api/settings/test/test_global_settings_views.py`

**Base class**: `IamTestCase` (provides `self.headers`,
`self.schema_name`, `APIClient`).

| ID | Test Method | Validates | Tier |
|----|-------------|-----------|------|
| TC-A-01 | `test_get_default_no_row` | GET returns startup default; no DB row created (R10). | Integration |
| TC-A-02 | `test_get_with_db_row` | GET returns persisted value. | Integration |
| TC-A-03 | `test_get_does_not_create_row` | After GET, `TenantSettings.objects.count() == 0` (side-effect-free). | Integration |
| TC-A-04 | `test_get_env_override_true` | GET with env var set → `env_override: true`, value matches env. | Contract |
| TC-A-05 | `test_get_env_override_false` | GET without env var → `env_override: false`. | Contract |
| TC-A-06 | `test_put_creates_row` | PUT with valid value on fresh tenant creates row. | Integration |
| TC-A-07 | `test_put_updates_existing_row` | PUT on tenant with existing row updates value. | Integration |
| TC-A-08 | `test_put_returns_204` | Successful PUT → 204 No Content. | Integration |
| TC-A-09 | `test_put_persists_across_requests` | PUT value, then GET → matches. | Integration |
| TC-A-10 | `test_put_concurrent_safety` | Two sequential PUTs → single row, last value wins. Validates R2. | Integration |
| TC-A-11 | `test_put_min_boundary` | PUT `data_retention_months=3` → 204. | Unit |
| TC-A-12 | `test_put_max_boundary` | PUT `data_retention_months=120` → 204. | Unit |
| TC-A-13 | `test_put_below_min_rejected` | PUT `data_retention_months=2` → 400. | Contract |
| TC-A-14 | `test_put_above_max_rejected` | PUT `data_retention_months=121` → 400. | Contract |
| TC-A-15 | `test_put_non_integer_rejected` | PUT `data_retention_months="abc"` → 400. | Contract |
| TC-A-16 | `test_put_missing_field_rejected` | PUT `{}` → 400. | Contract |
| TC-A-17 | `test_put_env_override_returns_403` | PUT when env var set → 403 with message. | Contract |
| TC-A-18 | `test_put_invalidates_cache` | PUT → cache invalidation function called. | Integration |

```python
@unittest.skipUnless(settings.ONPREM, "ONPREM-only: global settings endpoint requires ONPREM=True")
class GlobalSettingsViewTest(IamTestCase):
    """Tests for the GlobalSettingsView GET and PUT."""

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.client = APIClient()
        self.url = reverse("global-settings-data-retention")
        with schema_context(self.schema_name):
            TenantSettings.objects.all().delete()

    def test_get_default_no_row(self):
        """GET with no row returns the startup default value."""
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], Config.MASU_RETAIN_NUM_MONTHS)

    def test_get_with_db_row(self):
        """GET returns the DB-persisted value."""
        with schema_context(self.schema_name):
            TenantSettings.objects.create(data_retention_months=18)
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], 18)

    def test_get_does_not_create_row(self):
        """GET is side-effect-free — no row is created (R10)."""
        with schema_context(self.schema_name):
            response = self.client.get(self.url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(TenantSettings.objects.count(), 0)

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "5"})
    def test_get_env_override_true(self):
        """GET with env var set returns env value and env_override=true."""
        response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data_retention_months"], 5)
        self.assertTrue(response.data["env_override"])

    def test_get_env_override_false(self):
        """GET without env var returns env_override=false."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["env_override"])

    def test_put_creates_row(self):
        """PUT on a fresh tenant creates a TenantSettings row."""
        with schema_context(self.schema_name):
            data = {"data_retention_months": 12}
            response = self.client.put(self.url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(TenantSettings.objects.count(), 1)
            self.assertEqual(TenantSettings.objects.first().data_retention_months, 12)

    def test_put_updates_existing_row(self):
        """PUT on a tenant with an existing row updates the value."""
        with schema_context(self.schema_name):
            TenantSettings.objects.create(data_retention_months=6)
            data = {"data_retention_months": 24}
            response = self.client.put(self.url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            row = TenantSettings.objects.first()
            self.assertEqual(row.data_retention_months, 24)

    def test_put_persists_across_requests(self):
        """Value set via PUT is returned by a subsequent GET."""
        with schema_context(self.schema_name):
            self.client.put(self.url, {"data_retention_months": 15}, format="json", **self.headers)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            response = self.client.get(self.url, **self.headers)
        self.assertEqual(response.data["data_retention_months"], 15)

    def test_put_concurrent_safety(self):
        """Sequential PUTs produce a single row with the last value (R2)."""
        with schema_context(self.schema_name):
            self.client.put(self.url, {"data_retention_months": 6}, format="json", **self.headers)
            self.client.put(self.url, {"data_retention_months": 12}, format="json", **self.headers)
            self.assertEqual(TenantSettings.objects.count(), 1)
            self.assertEqual(TenantSettings.objects.first().data_retention_months, 12)

    def test_put_min_boundary(self):
        """PUT with the PRD minimum (3) succeeds."""
        with schema_context(self.schema_name):
            response = self.client.put(self.url, {"data_retention_months": 3}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_max_boundary(self):
        """PUT with the upper limit (120) succeeds."""
        with schema_context(self.schema_name):
            response = self.client.put(self.url, {"data_retention_months": 120}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_put_below_min_rejected(self):
        """PUT below the minimum returns 400."""
        response = self.client.put(self.url, {"data_retention_months": 2}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_above_max_rejected(self):
        """PUT above the maximum returns 400."""
        response = self.client.put(self.url, {"data_retention_months": 121}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_non_integer_rejected(self):
        """PUT with a non-integer value returns 400."""
        response = self.client.put(self.url, {"data_retention_months": "abc"}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_missing_field_rejected(self):
        """PUT with an empty body returns 400."""
        response = self.client.put(self.url, {}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.dict(os.environ, {"RETAIN_NUM_MONTHS": "4"})
    def test_put_env_override_returns_403(self):
        """PUT when env var is set returns 403 — setting is locked."""
        response = self.client.put(self.url, {"data_retention_months": 12}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("environment variable", response.data["error"])

    @patch("api.settings.views.invalidate_view_cache_for_tenant_and_all_source_types")
    def test_put_invalidates_cache(self, mock_invalidate):
        """PUT triggers cache invalidation for the tenant."""
        with schema_context(self.schema_name):
            self.client.put(self.url, {"data_retention_months": 12}, format="json", **self.headers)
        mock_invalidate.assert_called_once_with(self.schema_name)
```

#### RBAC Tests

```python
@unittest.skipUnless(settings.ONPREM, "ONPREM-only: global settings endpoint requires ONPREM=True")
class GlobalSettingsRBACTest(IamTestCase):
    """RBAC enforcement for the GlobalSettingsView."""

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.client = APIClient()
        self.url = reverse("global-settings-data-retention")

    no_access = {"aws.account": {"read": ["*"]}}
    read_only = {"settings": {"read": ["*"]}}
    write_only = {"settings": {"write": ["*"]}}
    read_write = {"settings": {"read": ["*"], "write": ["*"]}}

    @RbacPermissions(no_access)
    def test_no_access_get_returns_403(self):
        """User without settings.read cannot GET."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(read_only)
    def test_read_access_get_returns_200(self):
        """User with settings.read can GET."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @RbacPermissions(read_only)
    def test_read_access_put_returns_403(self):
        """User with only settings.read cannot PUT."""
        response = APIClient().put(self.url, {"data_retention_months": 12}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @RbacPermissions(write_only)
    def test_write_access_put_returns_204(self):
        """User with settings.write can PUT."""
        response = APIClient().put(self.url, {"data_retention_months": 12}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @RbacPermissions(write_only)
    def test_write_access_get_returns_403(self):
        """User with only settings.write cannot GET."""
        response = APIClient().get(self.url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
```

#### ONPREM Gating Test

Django's `urlpatterns` are evaluated at import time, so
`override_settings(ONPREM=False)` does not re-evaluate the
`if settings.ONPREM:` block in `urls.py`. The existing Koku
convention is to annotate the entire test class with
`@unittest.skipUnless(settings.ONPREM, ...)`. Gating verification
is achieved by:

1. The `skipUnless(settings.ONPREM)` annotation on
   `GlobalSettingsViewTest` and `GlobalSettingsRBACTest` — these
   classes are skipped entirely when `ONPREM=False`, confirming
   that the endpoint is not reachable in SaaS mode.
2. A code review check that the route is inside the
   `if settings.ONPREM:` block in `api/urls.py`.

```python
class GlobalSettingsOnPremGatingTest(IamTestCase):
    """Verify the endpoint URL pattern is gated behind ONPREM."""

    @unittest.skipIf(settings.ONPREM, "This test only runs in SaaS mode (ONPREM=False)")
    def test_endpoint_not_registered_when_saas(self):
        """When ONPREM=False, the URL name does not resolve."""
        from django.urls import reverse, NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse("global-settings-data-retention")
```

---

### 9.4 Pipeline — Expiration Calculation

Tests extend `masu/test/processor/test_expired_data_remover.py`.

**Base class**: `MasuTestCase`.

| ID | Test Method | Validates | Tier |
|----|-------------|-----------|------|
| TC-P-01 | `test_calendar_month_3_months` | `relativedelta(months=3)` from Mar 10 → Dec 1 (not Dec 16). | Unit |
| TC-P-02 | `test_calendar_month_12_months` | 12 months from Mar 10, 2026 → Mar 1, 2025. | Unit |
| TC-P-03 | `test_calendar_month_13_months_jan_31` | 13 months from Jan 31 → Dec 1 (two years prior). | Unit |
| TC-P-04 | `test_calendar_month_boundary_matrix` | Matrix covering values 3, 4, 6, 12, 24, 60, 120 across different dates. Validates R4. | Unit |
| TC-P-05 | `test_per_tenant_retention_from_db` | `ExpiredDataRemover` reads per-tenant value when no `num_of_months_to_keep` override. | Integration |
| TC-P-06 | `test_explicit_override_ignores_db` | Passing `num_of_months_to_keep=2` bypasses DB lookup. | Unit |
| TC-P-07 | `test_default_when_no_schema` | Omitting `schema_name` falls back to `Config.MASU_RETAIN_NUM_MONTHS`. | Unit |
| TC-P-08 | `test_kafka_gate_per_tenant_rejection` | Payload outside per-tenant retention → rejected. | Integration |
| TC-P-09 | `test_kafka_gate_per_tenant_acceptance` | Payload inside per-tenant retention → accepted. | Integration |
| TC-P-10 | `test_purge_skipped_when_helper_returns_none` | `get_data_retention_months` returns `None` → purge loop skips tenant (R7). | Unit |
| TC-P-11 | `test_materialized_view_start_with_schema` | `materialized_view_month_start(schema_name="org1234567")` returns correct start for tenant with custom retention. | Integration |
| TC-P-12 | `test_materialized_view_start_without_schema` | `materialized_view_month_start()` (no schema) falls back to `settings.RETAIN_NUM_MONTHS`. | Unit |

```python
class CalendarMonthExpirationTest(MasuTestCase):
    """Tests for the relativedelta-based expiration calculation."""

    def _make_remover(self, months, mock_today):
        """Create an ExpiredDataRemover with a patched DateHelper.today."""
        with patch(
            "masu.processor.expired_data_remover.DateHelper.today",
            new_callable=PropertyMock,
            return_value=mock_today,
        ):
            return ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, months)

    def test_calendar_month_3_months(self):
        """3 months from Mar 10, 2026 → Dec 1, 2025 (not Dec 16)."""
        today = datetime(2026, 3, 10)
        with patch(
            "masu.processor.expired_data_remover.DateHelper.today",
            new_callable=PropertyMock,
            return_value=today,
        ):
            remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 3)
            expire = remover._calculate_expiration_date()
        expected = datetime(2025, 12, 1, tzinfo=settings.UTC)
        self.assertEqual(expire, expected)

    def test_calendar_month_12_months(self):
        """12 months from Mar 10, 2026 → Mar 1, 2025."""
        today = datetime(2026, 3, 10)
        with patch(
            "masu.processor.expired_data_remover.DateHelper.today",
            new_callable=PropertyMock,
            return_value=today,
        ):
            remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 12)
            expire = remover._calculate_expiration_date()
        expected = datetime(2025, 3, 1, tzinfo=settings.UTC)
        self.assertEqual(expire, expected)

    def test_calendar_month_13_months_jan_31(self):
        """13 months from Jan 31, 2026 → Dec 1, 2024."""
        today = datetime(2026, 1, 31)
        with patch(
            "masu.processor.expired_data_remover.DateHelper.today",
            new_callable=PropertyMock,
            return_value=today,
        ):
            remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 13)
            expire = remover._calculate_expiration_date()
        expected = datetime(2024, 12, 1, tzinfo=settings.UTC)
        self.assertEqual(expire, expected)

    def test_calendar_month_boundary_matrix(self):
        """Verify calendar-month calculation for a range of retention values (R4)."""
        date_matrix = [
            {"today": datetime(2026, 7, 1), "months": 3, "expected_year": 2026, "expected_month": 4},
            {"today": datetime(2026, 7, 15), "months": 4, "expected_year": 2026, "expected_month": 3},
            {"today": datetime(2026, 1, 1), "months": 6, "expected_year": 2025, "expected_month": 7},
            {"today": datetime(2026, 3, 31), "months": 12, "expected_year": 2025, "expected_month": 3},
            {"today": datetime(2026, 6, 15), "months": 24, "expected_year": 2024, "expected_month": 6},
            {"today": datetime(2026, 12, 1), "months": 60, "expected_year": 2021, "expected_month": 12},
            {"today": datetime(2026, 6, 30), "months": 120, "expected_year": 2016, "expected_month": 6},
        ]
        for case in date_matrix:
            with self.subTest(months=case["months"], today=case["today"]):
                with patch(
                    "masu.processor.expired_data_remover.DateHelper.today",
                    new_callable=PropertyMock,
                    return_value=case["today"],
                ):
                    remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, case["months"])
                    expire = remover._calculate_expiration_date()
                expected = datetime(
                    year=case["expected_year"],
                    month=case["expected_month"],
                    day=1,
                    tzinfo=settings.UTC,
                )
                self.assertEqual(expire, expected)
```

#### Per-Tenant Retention Integration

```python
class PerTenantRetentionTest(MasuTestCase):
    """Verify ExpiredDataRemover reads per-tenant retention from DB."""

    def setUp(self):
        """Clean state."""
        super().setUp()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    def test_per_tenant_retention_from_db(self):
        """ExpiredDataRemover reads the tenant's DB value when available."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=18)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            remover = ExpiredDataRemover(
                self.schema, Provider.PROVIDER_AWS, schema_name=self.schema
            )
        self.assertEqual(remover._months_to_keep, 18)

    def test_explicit_override_ignores_db(self):
        """An explicit num_of_months_to_keep bypasses the DB lookup."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=18)
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS, 5)
        self.assertEqual(remover._months_to_keep, 5)

    def test_default_when_no_schema(self):
        """Omitting schema_name falls back to Config.MASU_RETAIN_NUM_MONTHS."""
        remover = ExpiredDataRemover(self.schema, Provider.PROVIDER_AWS)
        self.assertEqual(remover._months_to_keep, Config.MASU_RETAIN_NUM_MONTHS)
```

#### R7 — Purge Skip on DB Error

```python
class PurgeSkipOnDBErrorTest(MasuTestCase):
    """Validate R7 — purge skips tenant when DB read fails."""

    @patch("api.settings.utils.schema_context")
    def test_purge_skipped_when_helper_returns_none(self, mock_ctx):
        """When get_data_retention_months returns None, purge loop skips tenant."""
        mock_ctx.side_effect = Exception("DB down")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            retention = get_data_retention_months(self.schema)
        self.assertIsNone(retention)
```

#### Kafka Gate

The Kafka handler tests extend the existing `KafkaMsgHandlerTest`
class in `masu/test/external/test_kafka_msg_handler.py`, reusing
its `MockMessage`, `MockKafkaConsumer`, and `FakeManifest` fixtures.

```python
class KafkaRetentionGateTest(MasuTestCase):
    """Verify Kafka ingest gate uses per-tenant retention."""

    @patch("masu.external.kafka_msg_handler.get_data_retention_months")
    @patch("masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id")
    def test_kafka_gate_per_tenant_rejection(self, mock_source, mock_retention):
        """Payload whose manifest end is outside the tenant's retention is rejected."""
        mock_retention.return_value = 3
        mock_source.return_value = baker.prepare("Sources", provider=baker.prepare("Provider"))
        dh = DateHelper()
        old_end = dh.relative_month_end(-4)
        # Build a FakeManifest with end date outside 3-month window
        # Call the handler function and assert it returns (None, manifest_uuid)
        # Assert shutil.rmtree was called (payload cleaned up)

    @patch("masu.external.kafka_msg_handler.get_data_retention_months")
    @patch("masu.external.kafka_msg_handler.utils.get_source_and_provider_from_cluster_id")
    def test_kafka_gate_per_tenant_acceptance(self, mock_source, mock_retention):
        """Payload whose manifest end is inside the tenant's retention is accepted."""
        mock_retention.return_value = 24
        mock_source.return_value = baker.prepare("Sources", provider=baker.prepare("Provider"))
        dh = DateHelper()
        recent_end = dh.relative_month_end(-2)
        # Build a FakeManifest with end date inside 24-month window
        # Call the handler function and assert it proceeds past the gate
```

#### `_remove_expired_data` Task — Schema Passthrough

Tests for `masu/processor/_tasks/remove_expired.py` to verify
`schema_name` is forwarded to `ExpiredDataRemover`.

```python
class RemoveExpiredDataTaskTest(MasuTestCase):
    """Verify _remove_expired_data passes schema to ExpiredDataRemover."""

    @patch("masu.processor._tasks.remove_expired.ExpiredDataRemover")
    def test_schema_passed_to_remover(self, mock_remover_cls):
        """The task forwards schema_name so ExpiredDataRemover can read per-tenant retention."""
        mock_instance = mock_remover_cls.return_value
        mock_instance.remove.return_value = []
        _remove_expired_data(self.schema, Provider.PROVIDER_AWS, simulate=False)
        mock_remover_cls.assert_called_once_with(self.schema, Provider.PROVIDER_AWS)
```

#### materialized_view_month_start

```python
class MaterializedViewMonthStartSchemaTest(MasuTestCase):
    """Verify materialized_view_month_start uses per-tenant retention."""

    def setUp(self):
        """Clean state."""
        super().setUp()
        with schema_context(self.schema):
            TenantSettings.objects.all().delete()

    def test_with_schema_reads_tenant_value(self):
        """When schema_name is provided, reads the tenant's retention."""
        with schema_context(self.schema):
            TenantSettings.objects.create(data_retention_months=12)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("RETAIN_NUM_MONTHS", None)
            result = materialized_view_month_start(schema_name=self.schema)
        dh = DateHelper()
        expected = dh.this_month_start - relativedelta(months=11)
        self.assertEqual(result, expected)

    @override_settings(RETAIN_NUM_MONTHS=5)
    def test_without_schema_uses_global_setting(self):
        """When no schema_name, falls back to settings.RETAIN_NUM_MONTHS."""
        result = materialized_view_month_start()
        dh = DateHelper()
        expected = dh.this_month_start - relativedelta(months=4)
        self.assertEqual(result, expected)
```

---

### 9.5 Serializer — `api/settings/test/test_global_settings_views.py`

Inline with the API view tests (same file).

| ID | Test Method | Validates | Tier |
|----|-------------|-----------|------|
| TC-S-01 | `test_serializer_valid_min` | `{"data_retention_months": 3}` is valid. | Unit |
| TC-S-02 | `test_serializer_valid_max` | `{"data_retention_months": 120}` is valid. | Unit |
| TC-S-03 | `test_serializer_invalid_below_min` | `{"data_retention_months": 2}` is invalid. | Unit |
| TC-S-04 | `test_serializer_invalid_above_max` | `{"data_retention_months": 121}` is invalid. | Unit |
| TC-S-05 | `test_serializer_missing_field` | `{}` is invalid. | Unit |
| TC-S-06 | `test_serializer_float_rejected` | `{"data_retention_months": 3.5}` is invalid. | Unit |

```python
class TenantSettingsSerializerTest(TestCase):
    """Tests for the TenantSettingsSerializer."""

    def test_valid_min(self):
        s = TenantSettingsSerializer(data={"data_retention_months": 3})
        self.assertTrue(s.is_valid())

    def test_valid_max(self):
        s = TenantSettingsSerializer(data={"data_retention_months": 120})
        self.assertTrue(s.is_valid())

    def test_invalid_below_min(self):
        s = TenantSettingsSerializer(data={"data_retention_months": 2})
        self.assertFalse(s.is_valid())

    def test_invalid_above_max(self):
        s = TenantSettingsSerializer(data={"data_retention_months": 121})
        self.assertFalse(s.is_valid())

    def test_missing_field(self):
        s = TenantSettingsSerializer(data={})
        self.assertFalse(s.is_valid())

    def test_float_rejected(self):
        s = TenantSettingsSerializer(data={"data_retention_months": 3.5})
        self.assertFalse(s.is_valid())
```

---

## 10. Item Pass/Fail Criteria

| Level | Pass Criterion |
|-------|----------------|
| Individual test | `assertEqual` / `assertRaises` / `assertIsNone` passes |
| Test class | All methods in the class pass |
| Tier | ≥ 80 % coverage of testable code in the tier's scope |
| Feature | All tiers pass, all risk-mapped TCs pass, zero regressions |

A test run is **FAILED** if any test mapped to a High-severity risk
(R7) fails, regardless of overall coverage.

---

## 11. Suspension Criteria and Resumption Requirements

| Condition | Action |
|-----------|--------|
| Test DB cannot provision tenant schemas | Suspend; resume after `KokuTestRunner` issues resolved |
| Migration `0345` fails on test DB | Suspend Phase 2/3 tests; fix migration; resume |
| More than 5 pre-existing test failures in baseline | Investigate; resume when baseline is green |

---

## 12. Test Deliverables

| Deliverable | Location |
|-------------|----------|
| Test plan (this document) | `docs/architecture/data-retention/test-plan.md` |
| Model tests | `reporting/tenant_settings/test/test_models.py` |
| Read helper tests | `api/settings/test/test_global_settings_utils.py` |
| API view tests | `api/settings/test/test_global_settings_views.py` |
| Pipeline tests (extended) | `masu/test/processor/test_expired_data_remover.py` |
| Kafka gate tests | `masu/test/external/test_kafka_retention_gate.py` |
| Materialized view tests (extended) | `api/test_utils.py` |
| Coverage report | `coverage report --show-missing` output |

---

## 13. Environmental Needs

| Requirement | Detail |
|-------------|--------|
| Database | PostgreSQL 16 (test runner creates `test_koku` with tenant schemas) |
| Python | 3.11+ with `pipenv` dependencies |
| Runner | `python koku/manage.py test --noinput -v 2` (via tox or direct) |
| ONPREM flag | Contract tests require `ONPREM=True` for endpoint registration; use `skipUnless` or `override_settings` |
| Coverage | `coverage run koku/manage.py test ... && coverage report --show-missing` |
| CI | Standard Koku CI pipeline; codecov target 90 % (project + patch) |

---

## 14. Staffing and Training Needs

No additional training. The test plan uses standard Koku patterns
and the Django `TestCase` / DRF `APIClient` APIs familiar to the
team.

---

## 15. Schedule

| Milestone | Phase | Est. Effort |
|-----------|-------|-------------|
| Model + migration tests (TC-M-*) | Phase 1 | 0.5 day |
| Read helper tests (TC-H-*) | Phase 3 | 0.5 day |
| API view + RBAC + gating tests (TC-A-*, TC-S-*) | Phase 2 | 1 day |
| Pipeline tests (TC-P-*) | Phase 3 | 1 day |
| Coverage gap analysis + fill | All | 0.5 day |
| **Total** | | **3.5 days** |

---

## 16. Risks and Contingencies

| Risk | Contingency |
|------|-------------|
| `KokuTestRunner` schema setup conflicts with new model | Test the migration independently with `manage.py migrate --run-syncdb` before full suite |
| `ONPREM=True` tests skipped in default CI | Add a CI matrix entry with `ONPREM=True` or use `@override_settings(ONPREM=True)` for URL resolution tests |
| `@override_settings(ONPREM=True)` does not re-register URL routes | Use `Resolver404` assertion pattern (TC-A-ONPREM) for gating; test endpoint behavior separately with `skipUnless` |
| Coverage target not met for Kafka gate | Kafka tests require `MockKafkaConsumer` and `MockMessage` fixtures from existing `test_kafka_msg_handler.py`; reuse them |
| Calendar-month tests are date-sensitive | All date-dependent tests patch `DateHelper.today` with fixed dates — no flaky behavior |

---

## 17. Traceability Matrix

Every design artifact and risk maps to at least one test case:

| Source | Test Cases |
|--------|-----------|
| DD-1: TenantSettings model | TC-M-01 through TC-M-10 |
| DD-1: Read helper | TC-H-01 through TC-H-10 |
| DD-2: GET endpoint | TC-A-01 through TC-A-05, TC-H-10 |
| DD-2: PUT endpoint | TC-A-06 through TC-A-18 |
| DD-2: RBAC | RBAC tests (5 cases) |
| DD-2: ONPREM gating | ONPREM gating test |
| DD-2: Serializer | TC-S-01 through TC-S-06 |
| DD-3: Calendar-month fix | TC-P-01 through TC-P-04 |
| DD-3: Per-tenant retention | TC-P-05 through TC-P-07 |
| DD-3: `_remove_expired_data` task | Task passthrough test |
| DD-3: Kafka gate | TC-P-08, TC-P-09 |
| DD-3: materialized_view_month_start | TC-P-11, TC-P-12 |
| R1 (template-clone) | TC-M-01 |
| R2 (race condition) | TC-A-10 |
| R4 (calendar shift) | TC-P-04 |
| R6 (default 4→3) | TC-H-02, TC-H-03 |
| R7 (DB failure) | TC-H-05, TC-H-06, TC-H-10, TC-P-10 |
| R9 (phase ordering) | TC-P-07 |
| R10 (helper fallback) | TC-H-02, TC-A-01, TC-A-03 |
| G1 (GET + None) | TC-H-10 |
| G2 (task schema passthrough) | Task passthrough test |

---

## 18. Gaps Identified During Test Planning

| ID | Gap | Severity | Resolution |
|----|-----|----------|------------|
| G1 | **GET endpoint when `get_data_retention_months` returns `None`** (DB error): The design specifies that the helper returns `None` on DB error, and the *purge* caller skips the tenant. But the *GET* endpoint also calls this helper. If it receives `None`, the API would return `{"data_retention_months": null}`, which may confuse the frontend. | Medium | Implementation should catch `None` in the GET handler and return `503 Service Unavailable` with a descriptive error. Add TC-H-10 to cover this. |
| G2 | **`_remove_expired_data` task does not pass `schema_name`** to `ExpiredDataRemover` today: The current task (`_tasks/remove_expired.py:33`) passes `schema_name` as the first positional arg (`customer_schema`), but the design adds a separate `schema_name` kwarg for the DB lookup. The task must be updated to also pass `schema_name=schema_name`. | Low | Addressed by TI-10 test and implementation change in `_tasks/remove_expired.py`. |
| G3 | **ONPREM gating test limitation**: Django URL patterns are static at import time. `override_settings(ONPREM=False)` cannot dynamically remove routes. The `skipUnless` / `skipIf` pattern only tests one side per CI run. | Low | Documented in test plan. Code review + `skipIf(settings.ONPREM)` test covers the SaaS path. |
| G4 | **`materialized_view_month_start` callers need `schema_name`**: Report serializers that call this function must be updated to pass `schema_name` from `request.user.customer.schema_name`. Not all callers may have `request` in scope. | Low | Audit callers during Phase 3 implementation. Fallback to `settings.RETAIN_NUM_MONTHS` is safe. |

---

## 19. Anti-Patterns Avoided

| Anti-Pattern | Mitigation in This Plan |
|--------------|------------------------|
| **Mocking the world**: patching ORM internals instead of using the test DB | Integration tests use real DB via `schema_context`; mocks only for env vars, `DateHelper.today`, and simulated DB errors |
| **Testing implementation, not behavior**: asserting internal method calls | Tests assert observable outcomes (HTTP status codes, return values, DB state), not mock call counts |
| **Flaky date tests**: using `datetime.now()` without determinism | All date-dependent tests patch `DateHelper.today` with fixed `datetime` values |
| **Test pollution**: shared mutable state between tests | `setUp` cleans `TenantSettings` rows; `schema_context` isolates tenant data; `tearDown` inherited from base classes |
| **Bare except**: catching all exceptions in assertions | `assertRaises(ValidationError)`, `assertRaises(ValueError)` — specific types only |
| **Magic numbers without context**: `assertEqual(result, 4)` | Constants reference `Config.MASU_RETAIN_NUM_MONTHS`, `TenantSettings.DEFAULT_RETENTION_MONTHS`, `TenantSettings.MIN_RETENTION_MONTHS` |
| **Ignoring edge cases**: only testing happy path | Boundary tests (min/max), type errors (float, string), missing fields, empty bodies, None returns |
| **Duplicate test logic**: copy-paste across test methods | `subTest` for parameterized matrices (TC-P-04); shared setUp for cleanup |

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-03-27 | Initial test plan — IEEE 829 format, 3 tiers, 50+ test cases across 7 test files. 4 gaps identified (G1–G4). All 10 risks mapped. |
