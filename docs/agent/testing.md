# Agent Testing Guide

Compact reference for writing and running Koku unit tests.

## Running Tests

```bash
# Canonical (isolated venv)
pipenv run tox -- masu.test.path.to.test_module
pipenv run tox -- masu.test.path.to.test_module.ClassName.test_method

# Faster (current venv, from the repository root)
pipenv run python koku/manage.py test masu.test.path.to.test_module --no-input -v 2
```

Requires PostgreSQL 16 on `localhost:15432` (`postgres` / `postgres`). Test DB:
`test_postgres`. Set `KEEPDB=True` in `.env` to preserve between runs.

```bash
podman run -d --name koku-test-db -p 15432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
```

## Test Base Classes

| Class | Module | Use when |
|-------|--------|----------|
| `IamTestCase` | `api.iam.test.iam_test_case` | API tests needing identity/auth |
| `MasuTestCase` | `masu.test` | Masu/backend tests with provider fixtures |
| `TestCase` | `django.test` | Simple tests without provider data |

**IamTestCase:** `self.dh`, `self.schema_name` (`org1234567`), `self.tenant`,
`self.headers`, `self.request_context`, `self.factory`.

**MasuTestCase** (extends IamTestCase): `self.schema`, `self.ocp_provider` /
`self.ocp_provider_uuid`, `self.aws_provider` / `self.aws_provider_uuid`,
`self.azure_provider`, `self.gcp_provider`, `self.ocp_on_aws_ocp_provider` /
`self.ocpaws_provider_uuid`, `self.ocp_on_azure_ocp_provider`,
`self.ocp_on_gcp_ocp_provider`, `self.ocp_cluster_id` (`OCP-on-Prem`).

## Seeded Test Data

`KokuTestRunner.setup_databases()` seeds providers, report periods, summaries, and
cost models once via `ModelBakeryDataLoader`. Cluster IDs: `OCP-on-Prem`,
`OCP-on-AWS`, `OCP-on-Azure`, `OCP-on-GCP`.

## Required Mocks

External services are unavailable in unit tests. Mock at the **import location**
(the module under test), not where the symbol is defined.

| Service | Patch target | Return |
|---------|--------------|--------|
| Trino | `masu.database.ocp_report_db_accessor.trino_table_exists` | `False` |
| Trino | `masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino` | `False` |
| Unleash | `masu.database.ocp_report_db_accessor.is_feature_flag_enabled_by_schema` | `False` |
| Currency | `api.report.serializers.get_currency` | `"USD"` |

```python
# Correct
@patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)

# Wrong — patches definition site, not where ocp_report_db_accessor imports it
@patch("masu.util.common.trino_table_exists", return_value=False)
```

## Tenant Test Isolation

Clean up stale tenant data before creating fixtures:

```python
with schema_context(self.schema):
    CostModelMap.objects.filter(provider_uuid=self.ocp_provider_uuid).delete()
    cost_model = CostModel.objects.create(...)
    CostModelMap.objects.create(cost_model_id=cost_model.uuid, provider_uuid=...)
```

## Debugging Test DB

```bash
PGPASSWORD=postgres psql -h localhost -p 15432 -U postgres -d test_postgres
SET search_path TO org1234567;
```

## Python 3.11 Caveat

`self.skipTest()` inside `with self.subTest():` skips the **entire** test method,
not just the subtest (fixed in 3.12+). Split subtests into separate test methods.

## Conventions

- Place tests in `test/` next to the code; name files `test_*.py`
- Clean up temp files/dirs created during tests

## Test Data with model_bakery

```python
from model_bakery import baker

# ✅ GOOD - Use baker.make() for test objects
report = baker.make("OCPUsageReportPeriod", provider=self.ocp_provider_uuid)

# ❌ BAD - Manual object creation
report = OCPUsageReportPeriod.objects.create(...)
```

## subTest for Multiple Scenarios

Combine `schema_context` with `subTest` for clarity:
```python
with schema_context(self.schema), self.subTest("bill is created with original cluster alias"):
    report_period = OCPUsageReportPeriod.objects.get(...)
    self.assertEqual(report_period.cluster_alias, cluster_alias_orig)
```

## Mocking with Tuple Unpacking

```python
# ✅ GOOD - Tuple unpacking for multiple patches
with (
    patch("module.function_a") as mock_a,
    patch("module.function_b") as mock_b,
):
    # test code

# ❌ BAD - Nested with statements
with patch("module.function_a") as mock_a:
    with patch("module.function_b") as mock_b:
        # test code
```

## Assertions

- Use `self.assertEqual()` with descriptive expected values
- Verify mock calls: `mock.assert_called_once()`, `mock.assert_called_with(...)`
- Test edge cases: empty data, None values, boundary conditions
