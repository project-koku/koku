# Koku Ecosystem – AI Agent Guide

This document captures hard-won knowledge about the Koku codebase.
Follow it precisely. Never take shortcuts, never skip steps, never weaken
assertions or silently swallow errors to make things pass.

---

## Ecosystem Overview

Koku is the upstream of Red Hat Lightspeed Cost Management, an open-source
FinOps tool. The workspace contains three repositories under `~/dev/koku/`:

- **koku** (`~/dev/koku/koku/`) — Django backend (API, data pipeline, Celery workers)
- **koku-ui** (`~/dev/koku/koku-ui/`) — React frontend (monorepo: HCCM, ROS, on-prem shell)
- **koku-metrics-operator** (`~/dev/koku/koku-metrics-operator/`) — Go OpenShift operator

### Data Flow

```
OpenShift Cluster --> [Operator queries Prometheus/Thanos] --> CSV reports --> tar.gz upload
                                                                                    |
Cloud Providers --> [AWS CUR / Azure API / GCP BigQuery] ------> Koku Backend (Celery)
                                                                        |
                                                          PostgreSQL + Trino --> REST API
                                                                        |
                                                                   koku-ui (React)
```

### Critical Design Constraints

1. **Dual execution paths**: Every data feature must work in BOTH:
   - **Cloud** (console.redhat.com): Trino SQL for heavy aggregation + PostgreSQL for summaries
   - **On-prem**: PostgreSQL-only (no Trino)
2. **Multi-tenancy**: Schema-per-tenant via `django-tenants`. All queries must be tenant-aware.
3. **OCI is deprecated/removed** — do not implement OCI support.
4. **Feature flags** (Unleash): Only gate features behind flags when explicitly required.
5. **Supported providers**: AWS, Azure, GCP, OpenShift (and OCP-on-cloud: OCP_AWS, OCP_Azure, OCP_GCP).
6. **Default to on-prem mode**: Unless explicitly told otherwise, always start Cost Management services (koku-server, masu-server, koku-worker, koku-beat, etc.) with `ONPREM=True`. This uses the PostgreSQL-only code path and avoids requiring Trino, Hive Metastore, or other cloud-only infrastructure. In practice this means exporting `ONPREM=True` before running `docker compose up` (e.g. `export ONPREM=True && export USER_ID=$(id -u) && export GROUP_ID=$(id -g) && docker compose up -d ...`). Without this flag the ingestion pipeline will fail trying to connect to Trino.

---

# KOKU BACKEND (`~/dev/koku/koku/`)

## Tech Stack

| Component      | Technology                                        |
|----------------|---------------------------------------------------|
| Framework      | Django 5.2 + Django REST Framework 3.14+          |
| Database       | PostgreSQL 16 with `django-tenants` (schema-per-tenant) |
| Task Queue     | Celery + Redis/Valkey broker                      |
| Caching        | Redis (django-redis) — default, api, rbac, worker |
| Object Storage | S3/MinIO (CSV/Parquet files)                      |
| Analytics      | Trino (Hive catalog) — cloud only                 |
| Feature Flags  | Unleash                                           |
| Python         | 3.11                                              |
| Dependencies   | `Pipfile` / `pipenv` (no `requirements.txt`)      |

## Repository Layout

```
koku/                          # Repository root
├── koku/                      # Django project root (manage.py lives here)
│   ├── koku/                  # Django settings package (settings.py, urls.py, celery.py)
│   ├── api/                   # REST API: views, serializers, query handlers, IAM, providers
│   ├── cost_models/           # Cost model definitions (CostModel, CostModelMap) [TENANT]
│   ├── masu/                  # Data ingestion: downloaders, processors, DB accessors
│   │   ├── database/          # DB accessors and SQL templates
│   │   │   └── sql/           # Jinja2 SQL templates organized by provider
│   │   ├── processor/         # Cost updaters and data processors
│   │   └── test/              # Masu tests
│   ├── reporting/             # Reporting models (daily summaries, UI tables) [TENANT]
│   │   └── provider/          # Provider-specific models (ocp/, aws/, azure/, gcp/)
│   ├── reporting_common/      # Shared reporting utilities [SHARED]
│   ├── sources/               # Platform-Sources integration (Kafka)
│   ├── forecast/              # Cost forecasting
│   ├── hcs/                   # Hybrid Cloud Services
│   ├── subs/                  # Subscription extraction
│   ├── providers/             # Provider interface implementations
│   ├── kafka_utils/           # Kafka utilities
│   └── common/                # Shared utilities
├── db_functions/              # Raw SQL stored procedures (partitioning, schema cloning)
├── testing/                   # Integration test harness, test data, compose files
├── dev/                       # Development scripts, credentials templates
├── docs/                      # Architecture documentation
├── docker-compose.yml         # Full development environment
└── tox.ini                    # Test runner configuration
```

---

## Multi-Tenancy Architecture

This is the single most important thing to understand about Koku.

### Shared vs Tenant Apps

| Scope      | Apps                                                                    | Schema            |
|------------|-------------------------------------------------------------------------|-------------------|
| **SHARED** | `api`, `sources`, `reporting_common`, `key_metrics`, `masu`, builtins   | `public`          |
| **TENANT** | `reporting`, `cost_models`                                              | `org{org_id}`     |

Migrations run with `migrate_schemas` (django-tenants multiprocessing executor).

### Critical Rules

- **Models in `reporting` and `cost_models` live in tenant schemas.**
  You MUST use `schema_context(schema_name)` or `tenant_context(tenant)`
  before querying them. Failing to do so causes
  `ProgrammingError: relation "..." does not exist`.

- `schema_context` takes a **string** (schema name like `"org1234567"`).
- `tenant_context` takes a **Tenant model instance**.

```python
# Correct: querying a tenant model
from django_tenants.utils import schema_context
with schema_context(self.schema):
    rows = OCPUsageLineItemDailySummary.objects.filter(...)

# Correct: in API query handlers
from django_tenants.utils import tenant_context
with tenant_context(self.tenant):
    query = self.query_table.objects.filter(...)
```

- **Models in `api` (Provider, Customer, User, Sources) live in `public`.**
  No schema context needed.

### Schema Name Convention

- Test schema: `org1234567` — test account: `10001` — test org_id: `1234567`
- Additional test tenants: `org2222222`, `org3333333`

---

## Key Models

### Public Schema

| Model                    | App            | Purpose                                              |
|--------------------------|----------------|------------------------------------------------------|
| `Customer`               | `api.iam`      | Organization (has `schema_name`, `org_id`)           |
| `User`                   | `api.iam`      | User within a customer                               |
| `Tenant`                 | `api.iam`      | Django-tenants tenant (manages schema lifecycle)     |
| `Provider`               | `api.provider` | Cloud provider source (AWS, OCP, Azure, GCP, locals) |
| `ProviderAuthentication` | `api.provider` | Auth credentials (ARN, cluster_id, etc.)             |
| `ProviderBillingSource`  | `api.provider` | Billing data location (S3 bucket, etc.)              |
| `Sources`                | `api.provider` | Platform-Sources integration records                 |

### Tenant Schema

| Model                            | App                      | Purpose                                    |
|----------------------------------|--------------------------|--------------------------------------------|
| `CostModel`                      | `cost_models`            | Rate definitions, markup, distribution     |
| `CostModelMap`                   | `cost_models`            | Maps cost model to provider UUID           |
| `TenantAPIProvider`              | `reporting.provider`     | Tenant-scoped copy of provider info        |
| `OCPUsageReportPeriod`           | `reporting.provider.ocp` | OCP billing period metadata                |
| `OCPUsageLineItemDailySummary`   | `reporting.provider.ocp` | Main OCP daily summary (costs, usage)      |
| `OCPCostBreakdownP`              | `reporting.provider.ocp` | UI summary: cost breakdown by rate name    |
| Various `*SummaryP` models       | `reporting.provider.*`   | Partitioned UI summary tables              |

### Provider Type Constants

```python
Provider.PROVIDER_OCP          # "OCP"
Provider.PROVIDER_AWS          # "AWS"
Provider.PROVIDER_AWS_LOCAL    # "AWS-local" (dev/test)
Provider.PROVIDER_AZURE        # "Azure"
Provider.PROVIDER_AZURE_LOCAL  # "Azure-local"
Provider.PROVIDER_GCP          # "GCP"
Provider.PROVIDER_GCP_LOCAL    # "GCP-local"
```

### Model Families

| Provider  | Bill Model           | Line Item Summary                      | Summary Tables (P)                             |
|-----------|----------------------|----------------------------------------|------------------------------------------------|
| AWS       | AWSCostEntryBill     | AWSCostEntryLineItemDailySummary       | AWSCostSummaryP, AWSCostSummaryByServiceP, etc.|
| Azure     | AzureCostEntryBill   | AzureCostEntryLineItemDailySummary     | AzureCostSummaryP, etc.                        |
| GCP       | GCPCostEntryBill     | GCPCostEntryLineItemDailySummary       | GCPCostSummaryP, etc.                          |
| OCP       | OCPUsageReportPeriod | OCPUsageLineItemDailySummary           | OCPCostSummaryP, OCPPodSummaryP, etc.          |
| OCP-Cloud | (cross-reference)    | OCPAWSCostLineItemProjectDailySummaryP | OCPAWSCostSummaryP, etc.                       |

### Partitioned Tables and Migrations

All partitioned tables use **RANGE partitioning on `usage_start`** (monthly granularity) and have `_p` or `_P` suffix. Partitions are tracked in `partitioned_tables` within each tenant schema.

**Creating new partitioned tables:**
```python
migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
migrations.CreateModel(name="NewSummaryP", fields=[...]),
migrations.AddIndex(model_name="newsummaryp", index=...),
migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
```

**Adding columns to existing partitioned tables:** standard `AddField` — no `set_pg_extended_mode` needed.

**Trino/Hive tables:** NOT managed by Django migrations. Created at runtime by masu processors. Disabled on-prem.

---

## API Layer

**Base path:** `/api/cost-management/v1/`

| Group          | Path                                    | Purpose                              |
|----------------|-----------------------------------------|--------------------------------------|
| Sources        | `sources/`                              | Provider CRUD (ViewSet)              |
| Reports        | `reports/{aws,azure,gcp,openshift}/`    | Cost, instance types, storage        |
| Tags           | `tags/{aws,azure,gcp,openshift}/`       | Tag keys/values                      |
| Resource Types | `resource-types/`                       | Accounts, regions, services, clusters|
| Forecasts      | `forecasts/{aws,azure,gcp,openshift}/`  | Cost forecasts                       |
| Settings       | `settings/`                             | Tags, cost groups, AWS category keys |
| Ingress        | `ingress/reports/`                      | OCP report uploads                   |
| Cost Models    | `cost-models/`                          | Cost model CRUD                      |
| Status         | `status/`, `metrics/`, `openapi.json`   | Health and metrics                   |

### Report API Pattern (ProviderMap)

Report endpoints use `provider_map.py` files that map query parameters to database columns and SQL fragments. Each provider has its own defining:
- `tag_column` and column mappings for group_by/filter/order_by
- SQL annotations for cost calculations
- Trino vs PostgreSQL query variants

Key files:
- `api/report/{provider}/provider_map.py` — per-provider maps
- `api/report/all/openshift/provider_map.py` — OCP-all (cross-cloud) map
- `api/report/queries.py` — base query handler
- `api/report/{provider}/query_handler.py` — provider query handlers

Query handlers use `tenant_context(self.tenant)` for all ORM queries.

### PACK_DEFINITIONS (Response Format)

The OCP query handler uses `PACK_DEFINITIONS` to transform flat DB aggregates into nested JSON:
- `cost_raw` → `cost.raw`
- `cost_usage` → `cost.usage`
- `cost_markup` → `cost.markup`
- `cost_platform_distributed` → `cost.platform_distributed`
- `cost_worker_unallocated_distributed` → `cost.worker_unallocated_distributed`
- `cost_total` → `cost.total`

The `_pack_data_object()` method in `api/report/queries.py` performs this transformation.

### Serializer Patterns

Serializers validate query parameters. They often need a `request` context:

```python
serializer = OCPCostQueryParamSerializer(data=params, context={"request": request})
```

Some serializers call `get_currency()` which queries `UserSettings` (a tenant model). In tests, mock it:

```python
@patch("api.report.serializers.get_currency", return_value="USD")
```

### Authentication and Authorization

- **Identity:** `x-rh-identity` header (base64 JSON) with `identity` and `entitlements`
- **Middleware chain:** `IdentityHeaderMiddleware` → `KokuTenantMiddleware` → `KokuTenantSchemaExistsMiddleware`
- **RBAC:** `koku.rbac.RbacService` with Redis cache
- **Dev mode:** `DEVELOPMENT_IDENTITY` env var + `DevelopmentIdentityHeaderMiddleware`

---

## Data Pipeline (Celery)

**Flow:** Orchestrator → Download → Parquet conversion → S3 upload → Trino aggregation → PostgreSQL summary tables

Key pipeline components:
- `masu/processor/orchestrator.py` — Polls providers, starts manifest processing
- `masu/external/report_downloader.py` — Provider-specific downloaders
- `masu/processor/*_parquet_processor.py` — Parquet conversion per provider
- `masu/processor/report_summary_updater.py` — Triggers summary table updates
- `masu/database/*_report_db_accessor.py` — DB accessors per provider

**Celery queues:** Download, Summary, CostModel, Refresh, OCP, Priority, HCS, SUBS

---

## Cost Model System

### Cost Model Structure

`CostModel` stores rates as a JSONField list. Each rate has: `metric`, `cost_type` (Infrastructure/Supplementary), optional `description`, `name`, `tiered_rates` (usage-based), and/or `tag_rates` (tag key/value based). Markup is a separate JSONField (`{"value": N, "unit": "percent"}`). Distribution settings control how overhead is allocated.

`CostModelMap` links cost models to providers (many-to-many via `provider_uuid`).

### Cost Application Flow

Cost model costs are applied to `OCPUsageLineItemDailySummary` via SQL in this order (`OCPCostModelCostUpdater.update_summary_cost_model_costs`):

1. **Usage costs** (`usage_costs.sql`): Tiered rates for CPU, memory, volume → sets `cost_model_cpu_cost`, `cost_model_memory_cost`, `cost_model_volume_cost`, `cost_model_rate_name`
2. **VM usage costs**: Hourly VM/core rates
3. **Markup** (Django ORM): `infrastructure_raw_cost * markup_percentage` → sets `infrastructure_markup_cost`
4. **Monthly costs** (`monthly_cost_*.sql`): Node, cluster, PVC, VM monthly rates → separate rows per cost type
5. **Tag usage costs**: Tag-based rates → separate rows per tag key:value
6. **Distribution** (`distribute_*.sql`): Platform, worker, storage, network, GPU overhead → distributes proportionally by usage to user projects
7. **UI summary** (`ui_summary/reporting_ocp_*.sql`): Aggregates line items into partitioned summary tables for API queries

### Key Column: `cost_model_rate_type`

This column on `OCPUsageLineItemDailySummary` distinguishes cost categories:
- `Infrastructure`, `Supplementary` — direct cost model rates
- `platform_distributed` — distributed platform overhead
- `worker_distributed` — distributed worker unallocated
- `unattributed_storage`, `unattributed_network` — distributed overheads
- `gpu_distributed` — distributed GPU unallocated

The UI summary tables GROUP BY this column, which is how the API returns separate cost categories.

### SQL File Locations

Three SQL directories exist for different execution paths. Changes may need to be applied across all three:

- **`masu/database/sql/`** — Cloud PostgreSQL path (used alongside Trino)
- **`masu/database/trino_sql/`** — Trino/Hive path (cloud only, heavy aggregation)
- **`masu/database/self_hosted_sql/`** — On-prem PostgreSQL path (no Trino)

Key subdirectories within each:
- `openshift/cost_model/` — Cost model application SQL
- `openshift/cost_model/distribute_cost/` — Distribution SQL
- `openshift/ui_summary/` — UI summary table population SQL

SQL templates use Jinja2: `{{param}}` for bind parameters, `{{param | sqlsafe}}` for identifiers.

### CostModelDBAccessor Properties

- `infrastructure_rates` / `supplementary_rates` → `{metric: value}`
- `infrastructure_rates_by_name` / `supplementary_rates_by_name` → list of `{metric, value, name}`
- `tag_infrastructure_rates` / `tag_supplementary_rates` → tag-based rates
- `tag_rate_names` → `{metric: {tag_key: rate_name}}`
- `distribution_info` → distribution configuration dict
- `markup` → `{"value": Decimal, "unit": "percent"}`

### Metric Constants (`api.metrics.constants`)

```python
INFRASTRUCTURE_COST_TYPE = "Infrastructure"
SUPPLEMENTARY_COST_TYPE = "Supplementary"
PLATFORM_COST = "platform_cost"
WORKER_UNALLOCATED = "worker_unallocated"
STORAGE_UNATTRIBUTED = "storage_unattributed"
NETWORK_UNATTRIBUTED = "network_unattributed"
GPU_UNALLOCATED = "gpu_unallocated"
DISTRIBUTION_TYPE = "distribution_type"
DEFAULT_DISTRIBUTION_TYPE = "cpu"
```

---

## Common Utilities

### DateHelper (`api.utils.DateHelper`)

```python
dh.now, dh.now_utc, dh.today, dh.yesterday, dh.tomorrow
dh.this_month_start, dh.this_month_end
dh.last_month_start, dh.last_month_end
dh.days_in_month(date), dh.list_days(start, end)
dh.parse_to_date(input)  # converts string/datetime to date
```

### SummaryRangeConfig (`masu.util.common.SummaryRangeConfig`)

Pydantic model for date range configuration. Accepts `datetime` or `str`:

```python
summary_range = SummaryRangeConfig(start_date=self.dh.this_month_start, end_date=self.dh.today)
```

Properties: `start_of_month`, `end_of_month`, `is_current_month`, `summary_start`, `summary_end`, `iter_summary_range_by_month()`.

### Structured Logging

Always use `log_json()`:

```python
from api.common import log_json
LOG.info(log_json(msg="doing something", schema=self.schema, provider_uuid=uuid))
```

### Common Code Patterns

**DB Accessor (context manager):**
```python
with OCPReportDBAccessor(self.schema) as accessor:
    accessor.populate_usage_costs_by_name(...)
```

**SQL Execution:**
```python
sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/usage_costs.sql")
sql = sql.decode("utf-8")
self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="INSERT")
```

**Distribution SQL pattern** (5 CTEs): source costs → user usage sums → proportional distribution → source negation → INSERT both.

---

## Django ORM Gotchas

### Mixed-Type Aggregation

`Sum`, `Value(0)`, `Coalesce` with `DecimalField` columns will raise `FieldError: Expression contains mixed types` if `IntegerField` and `DecimalField` are mixed. Always set `output_field`:

```python
_decimal = DecimalField(max_digits=33, decimal_places=15)
qs.annotate(
    total=Sum(
        Coalesce(F("cost_model_cpu_cost"), Value(0, output_field=_decimal)),
        output_field=_decimal,
    )
)
```

### Foreign Key to TenantAPIProvider

`OCPUsageReportPeriod.provider` is a FK to `TenantAPIProvider` (tenant-scoped), NOT to `Provider` (public). Filter with `provider_id=uuid`:

```python
# Correct
OCPUsageReportPeriod.objects.filter(provider_id=self.ocp_provider_uuid)
# Wrong — ValueError about instance type mismatch
OCPUsageReportPeriod.objects.filter(provider=self.ocp_provider)
```

---

## Testing

### Running Tests

```bash
# Via tox (canonical, creates isolated venv):
tox -e py311
tox -e py311 -- masu.test.database.test_cost_breakdown_usage

# Direct (faster, uses current venv):
cd koku && pipenv run python koku/manage.py test masu.test.database.test_cost_breakdown_usage --no-input -v 2
```

### Test Base Classes

| Class          | Module                          | Use When                                     |
|----------------|---------------------------------|----------------------------------------------|
| `IamTestCase`  | `api.iam.test.iam_test_case`    | API tests needing identity/auth context      |
| `MasuTestCase` | `masu.test`                     | Masu/backend tests needing provider fixtures |
| `TestCase`     | `django.test`                   | Simple tests without provider data           |

**IamTestCase provides:** `self.dh` (DateHelper), `self.schema_name` (`"org1234567"`), `self.tenant` (Tenant), `self.headers` (identity headers), `self.request_context`, `self.factory` (RequestFactory).

**MasuTestCase provides (extends IamTestCase):** `self.schema`, `self.ocp_provider` / `self.ocp_provider_uuid` (OCP on-prem), `self.aws_provider` / `self.aws_provider_uuid`, `self.azure_provider`, `self.gcp_provider`, `self.ocp_on_aws_ocp_provider` / `self.ocpaws_provider_uuid`, `self.ocp_on_azure_ocp_provider`, `self.ocp_on_gcp_ocp_provider`, `self.ocp_cluster_id` (`"OCP-on-Prem"`).

### Test Data Seeding

Test data is seeded ONCE by `KokuTestRunner.setup_databases()` via `ModelBakeryDataLoader`. It creates providers, report periods, daily summary rows, cost models, and UI summary data. Cluster IDs: `"OCP-on-Prem"`, `"OCP-on-AWS"`, `"OCP-on-Azure"`, `"OCP-on-GCP"`.

`KEEPDB=True` in `.env` preserves the test database between runs. Test DB is `test_postgres` on port 15432.

### Database Requirement

Tests need PostgreSQL 16 on `localhost:15432` (user `postgres`, password `postgres`):

```bash
podman run -d --name koku-test-db -p 15432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
```

### What to Mock

External services are unavailable in unit tests. Always mock:

| Service      | What to mock                                                              | Return    |
|--------------|---------------------------------------------------------------------------|-----------|
| **Trino**    | `masu.database.ocp_report_db_accessor.trino_table_exists`                 | `False`   |
| **Trino**    | `masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino` | `False` |
| **Unleash**  | `masu.database.ocp_report_db_accessor.is_feature_flag_enabled_by_schema`  | `False`   |
| **Currency** | `api.report.serializers.get_currency`                                     | `"USD"`   |

**Mock at the import location, not the definition location:**

```python
# Correct
@patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
# Wrong
@patch("masu.util.common.trino_table_exists", return_value=False)
```

### Test Isolation with Tenant Data

When tests create tenant-scoped objects, always clean up stale data first:

```python
with schema_context(self.schema):
    CostModelMap.objects.filter(provider_uuid=self.ocp_provider_uuid).delete()
    cost_model = CostModel.objects.create(...)
    CostModelMap.objects.create(cost_model_id=cost_model.uuid, provider_uuid=...)
```

### Test Database Debugging

```bash
PGPASSWORD=postgres psql -h localhost -p 15432 -U postgres -d test_postgres
SET search_path TO org1234567;
```

### Python 3.11 Caveat

`self.skipTest()` inside `with self.subTest():` skips the ENTIRE test, not just the subtest (fixed in 3.12+). For 3.11, split subtests into separate test methods.

---

## Behavioral Rules for AI Agents

### Never Take Shortcuts

- Never wrap code in `try/except: pass` or `try/except: self.skipTest()` to make tests pass. Diagnose and fix the actual problem.
- Never weaken assertions (removing checks, replacing `assertEqual` with `assertTrue(True)`) to avoid failures.
- Never silently `continue` past failures in loops. Fix the issue, create proper fixture data, or split into separate tests with clear failure messages.
- Never return bogus/hardcoded data from mocks when the test intends to verify real behavior.

### Always Go the Extra Mile

- When a test fails due to missing fixture data, create the proper fixture data in `setUp`.
- When mocking external services, mock at the most precise level and only mock what is genuinely unavailable.
- When an assertion seems wrong, trace through the production code and SQL to understand WHY before changing it.
- Before modifying any test, read the production code it tests. Before modifying SQL, run it manually against the test DB. Before changing an assertion, verify the expected values by querying the database.

---

## Environment and Infrastructure

### Key Environment Variables (`.env`)

| Variable                       | Default       | Purpose              |
|--------------------------------|---------------|----------------------|
| `POSTGRES_SQL_SERVICE_HOST`    | `localhost`   | Database host        |
| `POSTGRES_SQL_SERVICE_PORT`    | `15432`       | Database port        |
| `DATABASE_USER`                | `postgres`    | Database user        |
| `DATABASE_PASSWORD`            | `postgres`    | Database password    |
| `DEVELOPMENT`                  | `True`        | Dev middleware       |
| `KEEPDB`                       | `True`        | Preserve test DB     |
| `S3_ENDPOINT`                  | MinIO URL     | Object storage       |
| `API_PATH_PREFIX`              | `/api/cost-management` | API URL prefix |

### Docker Compose Services

| Service          | Port  | Purpose                        |
|------------------|-------|--------------------------------|
| `db`             | 15432 | PostgreSQL 16                  |
| `valkey`         | 6379  | Redis-compatible cache/broker  |
| `koku-server`    | 8000  | API server                     |
| `masu-server`    | 5042  | Masu ingestion API             |
| `koku-worker`    | —     | Celery worker                  |
| `koku-beat`      | —     | Celery beat scheduler          |
| `trino`          | 8080  | Analytics SQL engine           |
| `hive-metastore` | 9083  | Hive metastore for Trino       |
| `minio`          | 9000  | S3-compatible object storage   |
| `unleash`        | 4242  | Feature flag server            |
| `grafana`        | 3001  | Monitoring dashboards          |
| `pgadmin`        | 8432  | Database admin UI              |

For tests, only PostgreSQL is required. Everything else should be mocked.

```bash
make docker-up          # Full stack
make docker-up-min      # Minimal (db, koku, masu, worker)
make docker-up-min-trino # Minimal + Trino
```

---

## Full Development Environment (On-Prem / PostgreSQL-Only)

This section describes how to bring up the entire Cost Management stack for local
development and testing, generate fake data, and verify the UI end-to-end.

### Prerequisites

- Docker / Podman with docker-compose support
- The three repos cloned under `~/dev/koku/`: `koku`, `koku-ui`, `nise`
- `USER_ID` and `GROUP_ID` set in `koku/.env` (run `id -u` and `id -g`)

### Step 1: Start Backend Services

The minimal on-prem stack needs: `db`, `valkey`, `unleash`, `koku-server`,
`masu-server`, `koku-worker`, `koku-beat`. MinIO is needed only during OCP data
ingestion (see Step 3).

```bash
cd ~/dev/koku/koku

# Ensure .env has USER_ID and GROUP_ID
grep -q USER_ID .env || echo "USER_ID=$(id -u)" >> .env
grep -q GROUP_ID .env || echo "GROUP_ID=$(id -g)" >> .env

# Start core services (no Trino, no MinIO yet)
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat
```

**Common port conflicts:**
- Port `15432` (db): Check for stale test containers: `podman ps -a | grep 15432`
- Port `9000` (MinIO): Conflicts with the frontend dev server. Stop the frontend
  before starting MinIO, and stop MinIO before restarting the frontend.

Wait for services to be healthy:

```bash
# Check all services are running
docker compose ps

# Verify API responds
curl -s http://localhost:8000/api/cost-management/v1/status/ | python3 -m json.tool
```

### Step 2: Verify Test Customer and Sources

The `create_test_customer.py` script (run automatically on first boot) creates a
test customer (`org_id: 1234567`, `account_number: 10001`) with pre-configured
sources:

```bash
docker compose exec db psql -U postgres -d postgres -c \
  "SELECT source_id, name, source_type FROM api_sources ORDER BY source_id;"
```

Expected sources:

| source_id | name                      | type       | cluster_id / notes                |
|-----------|---------------------------|------------|-----------------------------------|
| 1         | Test AWS Source            | AWS-local  | Reads from `/tmp/local_bucket`    |
| 2         | Test OCP on AWS           | OCP        | `my-ocp-cluster-1`               |
| 3         | Test OCP on Azure         | OCP        | `my-ocp-cluster-2`               |
| 4         | Test OCP on Premises      | OCP        | `my-ocp-cluster-3`               |
| 5         | Test Azure Source         | Azure-local|                                   |
| 7         | Test GCP Source           | GCP-local  |                                   |
| 8         | Test OCP on GCP           | OCP        | `test-ocp-gcp-cluster`           |

To check provider UUIDs and cluster IDs:

```bash
docker compose exec db psql -U postgres -d postgres -c "
  SELECT p.uuid::text, p.name, p.type, a.credentials
  FROM api_provider p
  LEFT JOIN api_providerauthentication a ON p.authentication_id = a.id
  ORDER BY p.name;"
```

### Step 3: Generate and Ingest OCP Test Data

OCP data flows through MinIO. The nise tool generates realistic usage CSVs.

#### 3a. Start MinIO (temporarily stop the frontend if it's on port 9000)

```bash
# Kill frontend if running on port 9000
lsof -ti :9000 | xargs kill 2>/dev/null

# Start MinIO and create buckets
docker compose up -d minio
sleep 3

docker run --rm --network koku_default --entrypoint sh minio/mc:latest -c "
  mc alias set local http://koku-minio:9000 kokuminioaccess kokuminiosecret &&
  mc mb --ignore-existing local/ocp-ingress &&
  mc mb --ignore-existing local/koku-bucket &&
  mc anonymous set public local/ocp-ingress &&
  mc anonymous set public local/koku-bucket
"
```

#### 3b. Generate OCP data with nise

The nise repo (`~/dev/koku/nise/`) has example YAMLs under `examples/`. Use them
as templates with updated dates.

```bash
cd ~/dev/koku/nise

# Create a date-adapted YAML (copy from examples/ocp_on_aws/ocp_static_data.yml,
# update start_date/end_date to current month range)
# Example: start_date: 2026-01-18, end_date: 2026-02-17

# Generate OCP data to a local directory
S3_ACCESS_KEY=kokuminioaccess \
S3_SECRET_KEY=kokuminiosecret \
S3_BUCKET_NAME=ocp-ingress \
.venv/bin/nise report ocp \
  --static-report-file /tmp/ocp_static_data.yml \
  --ocp-cluster-id my-ocp-cluster-1 \
  --insights-upload /tmp/nise_ocp_output \
  --daily-reports
```

**Nise CLI reference:**

| Provider | Command | Key flags |
|----------|---------|-----------|
| OCP | `nise report ocp` | `--ocp-cluster-id`, `--static-report-file`, `--insights-upload DIR`, `--minio-upload URL`, `--daily-reports` |
| AWS | `nise report aws` | `--static-report-file`, `--aws-s3-bucket-name LOCAL_DIR`, `--aws-s3-report-name None` |
| Azure | `nise report azure` | `--static-report-file`, `--azure-container-name LOCAL_DIR`, `--azure-report-name NAME` |
| GCP | `nise report gcp` | `--static-report-file`, `--gcp-bucket-name LOCAL_DIR`, `-r` |

**Nise environment variables** (required for MinIO upload):
- `S3_ACCESS_KEY` — MinIO access key (`kokuminioaccess`)
- `S3_SECRET_KEY` — MinIO secret key (`kokuminiosecret`)
- `S3_BUCKET_NAME` — Target bucket (`ocp-ingress`)

**Nise example YAMLs** (`~/dev/koku/nise/examples/`):
- `ocp_on_aws/ocp_static_data.yml` — OCP cluster (4 nodes, 6 namespaces, no GPUs)
- `ocp_on_aws/aws_static_data.yml` — Matching AWS infrastructure (EC2, EBS, S3, RDS, etc.)
- `ocp_on_azure/` — OCP + Azure variants
- `ocp_on_gcp/` — OCP + GCP variants

The koku repo also has templates under `dev/scripts/nise_ymls/` with Jinja2 date
placeholders, rendered by `dev/scripts/render_nise_yamls.py`.

#### 3c. Package and upload OCP data to MinIO

```bash
PAYLOAD=$(python3 -c "import uuid; print(uuid.uuid4().hex)")

# Create tarballs for each month
cd /tmp/nise_ocp_output/my-ocp-cluster-1/20260101-20260201
tar czf /tmp/${PAYLOAD}.2026_01.tar.gz .

cd /tmp/nise_ocp_output/my-ocp-cluster-1/20260201-20260301
tar czf /tmp/${PAYLOAD}.2026_02.tar.gz .

# Upload to MinIO (key names must NOT have .tar.gz extension)
docker run --rm --network koku_default \
  -v /tmp/${PAYLOAD}.2026_01.tar.gz:/data/${PAYLOAD}.2026_01 \
  -v /tmp/${PAYLOAD}.2026_02.tar.gz:/data/${PAYLOAD}.2026_02 \
  --entrypoint sh minio/mc:latest -c "
    mc alias set local http://koku-minio:9000 kokuminioaccess kokuminiosecret &&
    mc cp /data/${PAYLOAD}.2026_01 local/ocp-ingress/${PAYLOAD}.2026_01 &&
    mc cp /data/${PAYLOAD}.2026_02 local/ocp-ingress/${PAYLOAD}.2026_02
  "
```

**CRITICAL:** The MinIO object key must match exactly what the `ingest_ocp_payload`
endpoint expects: `{payload_name}.{YYYY_MM}` — **no `.tar.gz` extension**. The Masu
download code constructs a presigned URL using the payload name directly as the key.

#### 3d. Trigger OCP ingestion

```bash
# Enable OCP tags (required for tag-based cost models)
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"schema":"org1234567","action":"create","tag_keys":["environment","app","version","storageclass"],"provider_type":"ocp"}' \
  http://localhost:5042/api/cost-management/v1/enabled_tags/

# Trigger ingestion for each month
curl -s "http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567&payload_name=${PAYLOAD}.2026_01"
curl -s "http://localhost:5042/api/cost-management/v1/ingest_ocp_payload/?org_id=1234567&payload_name=${PAYLOAD}.2026_02"
```

#### 3e. Monitor ingestion progress

```bash
# Watch masu-server for extraction status
docker compose logs --since=2m masu-server 2>&1 | grep -i "extract\|error"

# Watch worker for processing and summarization
docker compose logs --since=2m koku-worker 2>&1 | grep -iE "summary|rows|complete|error|cost_model"
```

Ingestion is complete when you see `manifest marked complete` in the worker logs.

#### 3f. Stop MinIO after ingestion

```bash
docker compose stop minio
```

### Step 4: Generate AWS/Azure/GCP Local Data (Cloud Providers)

**On-prem limitation:** In `ONPREM=True` mode, only OCP data can be processed.
AWS-local, Azure-local, and GCP-local processors throw `NotImplementedError:
...does not implement write_to_self_hosted_table`. Cloud-local data works only
in the full Trino stack.

For the full (non-on-prem) stack, cloud data goes to local directories mapped
into the worker container:

| Provider   | Host path                                    | Container path             |
|------------|----------------------------------------------|----------------------------|
| AWS-local  | `testing/local_providers/aws_local/`         | `/tmp/local_bucket`        |
| Azure-local| `testing/local_providers/azure_local/`       | `/tmp/local_container`     |
| GCP-local  | `testing/local_providers/gcp_local/`         | `/tmp/gcp_local_bucket`    |

```bash
# Generate AWS data (writes directly to local directory)
cd ~/dev/koku/nise
.venv/bin/nise report aws \
  --static-report-file /tmp/aws_static_data.yml \
  --aws-s3-report-name None \
  --aws-s3-bucket-name ~/dev/koku/koku/testing/local_providers/aws_local

# Trigger download for AWS
curl -s "http://localhost:5042/api/cost-management/v1/download/?provider_uuid=<AWS_PROVIDER_UUID>"
```

### Step 5: Set Up Cost Models

Cost models define rates that convert usage data into dollar costs. Without rates,
all cost values will be `0.00`. The test customer has pre-created cost models, but
they may have **empty rates** by default.

#### Check existing cost models

```bash
docker compose exec db psql -U postgres -d postgres -c "
  SELECT cm.name, cm.source_type, cm.rates
  FROM \"org1234567\".cost_model cm;"
```

#### Update cost model with rates via API

```bash
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

curl -s -X PUT \
  -H "x-rh-identity: $IDENTITY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Cost Management OpenShift on AWS Cost Model",
    "description": "OCP on AWS with supplementary rates",
    "source_type": "OCP",
    "source_uuids": ["<PROVIDER_UUID>"],
    "distribution": "cpu",
    "distribution_info": {
      "distribution_type": "cpu",
      "platform_cost": true,
      "worker_cost": true
    },
    "rates": [
      {"metric":{"name":"cpu_core_usage_per_hour"},"tiered_rates":[{"unit":"USD","value":0.007}],"cost_type":"Supplementary","name":"CPU usage"},
      {"metric":{"name":"cpu_core_request_per_hour"},"tiered_rates":[{"unit":"USD","value":0.2}],"cost_type":"Supplementary","name":"CPU request"},
      {"metric":{"name":"memory_gb_usage_per_hour"},"tiered_rates":[{"unit":"USD","value":0.009}],"cost_type":"Supplementary","name":"Memory usage"},
      {"metric":{"name":"memory_gb_request_per_hour"},"tiered_rates":[{"unit":"USD","value":0.05}],"cost_type":"Supplementary","name":"Memory request"},
      {"metric":{"name":"storage_gb_usage_per_month"},"tiered_rates":[{"unit":"USD","value":0.01}],"cost_type":"Supplementary","name":"Storage usage"},
      {"metric":{"name":"storage_gb_request_per_month"},"tiered_rates":[{"unit":"USD","value":0.01}],"cost_type":"Supplementary","name":"Storage request"},
      {"metric":{"name":"node_cost_per_month"},"tiered_rates":[{"unit":"USD","value":1000}],"cost_type":"Infrastructure","name":"Node cost"},
      {"metric":{"name":"cluster_cost_per_month"},"tiered_rates":[{"unit":"USD","value":10000}],"cost_type":"Infrastructure","name":"Cluster cost"}
    ],
    "markup": {"value": 10, "unit": "percent"}
  }' \
  "http://localhost:8000/api/cost-management/v1/cost-models/<COST_MODEL_UUID>/"
```

**Important:** Each rate object MUST include a `name` field (string) — the API
returns `400: "This field is required"` without it.

Updating a cost model via the API automatically triggers a cost recalculation
in the worker. You can also trigger it manually:

```bash
curl -s "http://localhost:5042/api/cost-management/v1/update_cost_model_costs/?provider_uuid=<UUID>&schema=org1234567"
```

Pre-built cost model JSON files are in `dev/scripts/cost_models/`:
- `openshift_on_prem_cost_model.json` — Full OCP rates (CPU, memory, storage, node, cluster, tags)
- `openshift_on_aws_cost_model.json` — Markup-only (10%, empty rates by default)
- `aws_cost_model.json`, `azure_cost_model.json`, `gcp_cost_model.json`

### Step 6: Start the Frontend

```bash
cd ~/dev/koku/koku-ui

# Build the identity token
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

API_PROXY_URL=http://localhost:8000 \
API_TOKEN=$IDENTITY \
npm run start --workspace apps/koku-ui-onprem
```

The frontend starts at `http://localhost:9000/`. The webpack dev server proxies
`/api/cost-management/v1/*` to the backend at `http://localhost:8000`.

**Proxy configuration** (`apps/koku-ui-onprem/webpack.config.ts`):
- The proxy sends the identity via the `x-rh-identity` header (set from `API_TOKEN`)
- The proxy must NOT rewrite the path — the backend expects the full
  `/api/cost-management/v1/...` prefix

**Port 9000 conflict with MinIO:** The frontend and MinIO both use port 9000.
Never run them simultaneously. Stop MinIO before starting the frontend, and
vice versa.

### Step 7: Verify Data in the API

```bash
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)

# Check OCP costs by project
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8000/api/cost-management/v1/reports/openshift/costs/?filter[time_scope_value]=-1&filter[time_scope_units]=month&group_by[project]=*' \
  | python3 -m json.tool

# Check OCP compute usage
curl -s -H "x-rh-identity: $IDENTITY" \
  'http://localhost:8000/api/cost-management/v1/reports/openshift/compute/?filter[time_scope_value]=-1&filter[time_scope_units]=month&group_by[cluster]=*' \
  | python3 -m json.tool
```

If costs are all `0.00` but usage values are non-zero, the cost model either has
empty rates or wasn't applied. Check the cost model (Step 5) and trigger a
recalculation.

### Useful Masu API Endpoints

All endpoints are on the Masu server (`http://localhost:5042/api/cost-management/v1/`):

| Endpoint | Method | Purpose | Key params |
|----------|--------|---------|------------|
| `ingest_ocp_payload/` | GET | Trigger OCP data ingestion from MinIO | `org_id`, `payload_name` |
| `download/` | GET | Trigger provider data download | `provider_uuid` |
| `update_cost_model_costs/` | GET | Re-apply cost model rates | `provider_uuid`, `schema` |
| `enabled_tags/` | POST | Enable tag keys for filtering | `schema`, `tag_keys`, `provider_type`, `action` |
| `status/` | GET | Masu health check | — |

### Identity Header

All Koku API requests require an `x-rh-identity` header (base64-encoded JSON).
The development identity for the test customer:

```json
{
  "identity": {
    "account_number": "10001",
    "org_id": "1234567",
    "type": "User",
    "user": {
      "username": "user_dev",
      "email": "user_dev@foo.com",
      "is_org_admin": true,
      "access": {}
    }
  },
  "entitlements": {
    "cost_management": {
      "is_entitled": true
    }
  }
}
```

Generate the base64 token:

```bash
echo -n '<JSON above, minified>' | base64 -w0
```

When `DEVELOPMENT=True` is set in `.env`, the backend also reads
`DEVELOPMENT_IDENTITY` from `.env` as a fallback when no header is provided.
However, explicit headers are needed for the frontend proxy and direct API calls.

### Quick-Start Cheat Sheet

```bash
# 1. Start backend
cd ~/dev/koku/koku
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat

# 2. Generate + ingest OCP data (stop frontend first if running)
lsof -ti :9000 | xargs kill 2>/dev/null
docker compose up -d minio
# ... (generate nise data, upload to MinIO, trigger ingest — see Steps 3a-3e)
docker compose stop minio

# 3. Start frontend
cd ~/dev/koku/koku-ui
IDENTITY=$(echo -n '...' | base64 -w0)
API_PROXY_URL=http://localhost:8000 API_TOKEN=$IDENTITY npm run start --workspace apps/koku-ui-onprem

# 4. Open browser to http://localhost:9000/
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `address already in use :15432` | Stale test DB container | `podman stop koku-test-db` |
| `address already in use :9000` | Frontend or MinIO conflict | Kill the other process: `lsof -ti :9000 \| xargs kill` |
| MinIO `404 Not Found` on ingest | Object key has `.tar.gz` extension | Upload without extension: key must be `payload.YYYY_MM` not `payload.YYYY_MM.tar.gz` |
| Nise exits silently (code 0, no output) | Missing env vars for MinIO upload | Set `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME` before running nise |
| All costs `0.00` but usage non-zero | Cost model has empty `rates: []` | Update cost model with actual rates via API (Step 5) |
| `NotImplementedError: ...write_to_self_hosted_table` | AWS/Azure/GCP data in on-prem mode | On-prem only supports OCP data; use Trino stack for cloud providers |
| `operator does not exist: text ->> unknown` | GPU cost model SQL bug in on-prem | Use OCP data without GPU nodes (nise `ocp_on_aws` examples have no GPUs) |
| API returns `403 Forbidden` | Wrong identity header | Use `account_number: "10001"`, `org_id: "1234567"` (matches test customer) |
| Frontend proxy returns `404` | `pathRewrite` strips API prefix | Remove `pathRewrite` from `webpack.config.ts` — backend expects full `/api/cost-management/v1/` path |
| `mc: config is not a recognized command` | Old MinIO `mc` CLI version | Use `mc alias set` instead of `mc config host add` |
| API returns correct data but UI shows stale values | Django `cache_page` + browser HTTP cache | Flush server cache: `docker exec koku_valkey redis-cli FLUSHALL`, then hard-refresh browser (`Ctrl+Shift+R`) |
| Breakdown values are cluster-wide instead of per-project | `_breakdown_query_filter` missing entity filter | Fixed: `_apply_entity_scope()` now checks `group_by`, `filter`, and `exact:` prefixed variants |

### Cache Flushing (Important!)

The Koku API uses Django `cache_page` (backed by Valkey/Redis) with a 1-hour
default TTL. After ANY backend code change that affects API responses, you MUST:

```bash
# 1. Restart the server (picks up code changes from mounted volume)
docker compose restart koku-server

# 2. Flush the server-side cache
docker exec koku_valkey redis-cli FLUSHALL

# 3. Hard-refresh the browser (Ctrl+Shift+R) to bypass browser HTTP cache
```

Forgetting step 2 or 3 is the #1 cause of "I fixed it but it's still broken".

### Resuming After a Reboot

```bash
cd ~/dev/koku/koku

# Start the backend stack
docker compose up -d db valkey unleash koku-server masu-server koku-worker koku-beat

# Wait for services to be ready (~15 seconds)
sleep 15

# Flush cache to ensure fresh responses
docker exec koku_valkey redis-cli FLUSHALL

# Verify the API is responding
IDENTITY=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0)
curl -s -H "x-rh-identity: $IDENTITY" http://localhost:8000/api/cost-management/v1/reports/openshift/costs/ | python3 -c "import json,sys; d=json.load(sys.stdin); print('API OK, total:', d['meta']['total']['cost']['total']['value'])"

# Start the frontend (on-prem mode)
cd ~/dev/koku/koku-ui
# Kill anything on port 9000 first
lsof -ti :9000 | xargs kill 2>/dev/null || true
API_TOKEN=$(echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0) npx webpack serve --config apps/koku-ui-onprem/webpack.config.ts &

# Open browser to http://localhost:9000/openshift/details
```

**Data and cost models persist** in the PostgreSQL volume across reboots —
no need to re-ingest or re-apply cost models.

### Database Queries for Debugging

```bash
# Connect to the development database
docker compose exec db psql -U postgres -d postgres

# Check sources and providers
SELECT source_id, name, source_type, koku_uuid FROM api_sources ORDER BY source_id;

# Check cost models and their rates
SELECT cm.name, cm.source_type, cm.rates FROM "org1234567".cost_model cm;

# Check cost model assignments
SELECT cm.name, cmp.provider_uuid::text
FROM "org1234567".cost_model cm
JOIN "org1234567".cost_model_map cmp ON cm.uuid = cmp.cost_model_id;

# Check OCP daily summary data (are costs populated?)
SELECT usage_start, cluster_id, namespace,
       SUM(pod_usage_cpu_core_hours) AS cpu_hours,
       SUM(cost_model_cpu_cost) AS cpu_cost,
       SUM(infrastructure_raw_cost) AS infra_cost
FROM "org1234567".reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '2026-02-01'
GROUP BY usage_start, cluster_id, namespace
ORDER BY usage_start, namespace
LIMIT 20;

# Check manifest processing status
SELECT id, provider_id::text, assembly_id, num_total_files, num_processed_files, completed_datetime
FROM reporting_common_costusagereportmanifest
ORDER BY id DESC LIMIT 10;
```

---

## Cross-Cutting Patterns

### Adding a New Report API Endpoint

1. **Model** (`reporting/provider/{provider}/models.py`): Define partitioned summary table (suffix `P`) with `PartitionInfo`
2. **Migration** (`reporting/migrations/`): Create with `set_pg_extended_mode` pattern
3. **DB Accessor** (`masu/database/{provider}_report_db_accessor.py`): Add summary SQL for both Trino and PostgreSQL paths
4. **Provider Map** (`api/report/{provider}/provider_map.py`): Map query params to DB columns
5. **Query Handler** (`api/report/{provider}/query_handler.py`): Wire up query execution
6. **Serializer** (`api/report/{provider}/serializers.py`): Define request/response serialization
7. **View** (`api/report/{provider}/view.py`): Create DRF view
8. **URLs** (`api/urls.py`): Register new endpoint
9. **Tests**: Unit tests for model, accessor, provider_map, query_handler, view

### Adding a New Column to Existing Summary Tables

1. **Model**: Add field to the `*P` model
2. **Migration**: Standard `AddField` (no extended mode needed)
3. **DB Accessor**: Update summary SQL to populate the new column
4. **Provider Map**: Add column mapping if exposed via API
5. **Tests**: Update existing tests

### Trino vs PostgreSQL Dual-Path

- `masu/database/{provider}_report_db_accessor.py` contains both Trino SQL and PostgreSQL SQL
- Cloud: Trino aggregates Parquet on S3 → writes to PostgreSQL summary tables
- On-prem: Direct PostgreSQL SQL aggregation (no Trino)
- Trino tables created at runtime by `masu/processor/report_parquet_processor_base.py`

---

# KOKU-UI FRONTEND (`~/dev/koku/koku-ui/`)

## Tech Stack

| Layer          | Technology                                   |
|----------------|----------------------------------------------|
| Framework      | React 18 + TypeScript                        |
| State          | Redux + Redux Toolkit + Redux Thunk          |
| UI Library     | PatternFly 6 (Red Hat design system)         |
| Routing        | react-router-dom v6                          |
| HTTP Client    | Axios                                        |
| i18n           | react-intl + FormatJS                        |
| Build          | fec (frontend-components-config) / Webpack 5 |
| Feature Flags  | Unleash (@unleash/proxy-client-react)        |

## Monorepo Structure

```
koku-ui/
├── apps/
│   ├── koku-ui-hccm/       # Main Cost Management UI
│   ├── koku-ui-ros/        # Resource Optimization Service UI
│   └── koku-ui-onprem/     # On-prem shell (Module Federation)
├── libs/
│   ├── ui-lib/             # Shared components
│   └── onprem-cloud-deps/  # On-prem dependency shims
```

## Key Routes (HCCM)

| Path                                       | Feature                |
|--------------------------------------------|------------------------|
| `/`                                        | Overview dashboard     |
| `/aws`, `/azure`, `/gcp`, `/ocp`           | Provider cost details  |
| `/{provider}/breakdown`                    | Cost breakdown         |
| `/explorer`                                | Cost Explorer          |
| `/optimizations`                           | Optimizations (ROS)    |
| `/settings`                                | Settings               |

API base URL: `/api/cost-management/v1/` (Axios instance in `api/api.ts`)

---

# KOKU-METRICS-OPERATOR (`~/dev/koku/koku-metrics-operator/`)

## Tech Stack

| Component          | Technology                                |
|--------------------|-------------------------------------------|
| Language           | Go 1.25                                   |
| Operator SDK       | v1.41.1 (Kubebuilder v4)                 |
| Controller Runtime | sigs.k8s.io/controller-runtime v0.23.1   |
| Min OpenShift      | 4.12                                      |

## CRD: CostManagementMetricsConfig

Group: `costmanagement-metrics-cfg.openshift.io`, Version: `v1beta1`

Key spec fields: `api_url`, `authentication` (token/basic/service-account), `prometheus_config`, `upload` (cycle, toggle), `source`, `packaging` (max_size_MB), `volume_claim_template`

## Reconciliation Flow

1. Copy spec to status with defaults
2. Ensure PVC exists
3. Read cluster ID from ClusterVersion CR
4. Compute Prometheus query time range
5. Query Prometheus/Thanos for each hour
6. Generate CSV reports (node, pod, storage, VM, namespace, GPU metrics)
7. Package CSVs into tar.gz with manifest
8. Upload to `{api_url}/api/ingress/v1/upload`
9. Check/create source in Sources API
10. Cleanup old packages

```bash
make build        # Build manager binary
make test         # Run tests (Ginkgo + envtest)
make docker-build # Build container image
make deploy       # Deploy operator via Kustomize
```
