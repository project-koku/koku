# Koku development notes

## Quick reference

**Key commands:**
```
make docker-up-min          # start dev stack (PG, Redis, Minio, Trino, workers)
make serve                  # Django dev server (:8000)
make run-migrations         # apply pending migrations
make lint                   # pre-commit checks
pipenv run tox              # run test suite
make docker-reinitdb        # nuke + rebuild DB from scratch
```

**Project structure:**
```
koku/api/                   # REST API views, serializers, URL routing
koku/cost_models/           # cost model CRUD, rate sync, price lists
koku/koku/                  # Django project config (settings, database, feature flags)
koku/masu/                  # data pipeline: processors, Celery tasks, SQL templates
koku/masu/database/sql/     # PostgreSQL SQL templates (SaaS + on-prem)
koku/masu/database/trino_sql/       # SaaS-only Trino SQL templates
koku/masu/database/self_hosted_sql/ # on-prem-only PostgreSQL SQL templates
koku/reporting/             # Django models, migrations (reporting app)
deploy/                     # ClowdApp, kustomize, deployment configs
docs/specs/openapi.json     # OpenAPI spec (main API)
```

**Dev stack:** PostgreSQL :15432, Valkey :6379, S4 (S3-compat) :7480, Trino :8080

## PR workflow and releases

1. Open PRs as **DRAFT**.  Mark **Ready for Review** when done.
2. Add the `smoke-test` label to kick off IQE smoke tests.
3. Smoke tests **must pass** before merging (unless the PR only touches
   non-build files like docs).
4. Merges to `main` **auto-deploy to stage**.
5. Production releases are manual — Mon/Thu cadence via app-interface MRs.
   Use `make get-release-commit` to get the right commit hash (the commit
   before midnight UTC, so IQE has tested it).
6. Run `pre-commit run --all-files` before pushing.  Also run gitleaks
   with Red Hat patterns: `pre-commit run --config ~/.config/pre-commit/config.yaml`.

## Feature flags (Unleash) — gate risky changes

New features, SQL pipeline changes, and any code path change that could
negatively affect production **must** be gated behind an Unleash feature flag
with a default of **OFF** (`dev_fallback=True` for dev/test).

**What must be flagged:**
- New or changed SQL INSERT/UPDATE/DELETE templates in the pipeline
- New pipeline steps or changes to the cost model update flow
- New tables, FK relationships, or changes to FK on_delete behavior
- Changes to data written to reporting/summary tables

API-only additions that are purely additive (new endpoints, new optional
fields) may skip flagging if they don't affect data processing.

**Pattern:**

```python
# 1. Define in koku/masu/processor/__init__.py
MY_FEATURE_UNLEASH_FLAG = "cost-management.backend.my_feature_name"

# 2. Gate the code path
from masu.processor import is_feature_flag_enabled_by_schema, MY_FEATURE_UNLEASH_FLAG

if is_feature_flag_enabled_by_schema(schema, MY_FEATURE_UNLEASH_FLAG, dev_fallback=True):
    # new path
else:
    # legacy path — must remain functional
```

The legacy path must remain functional and tested.  Do not delete legacy SQL
files or code until the flag has been enabled in production for at least one
full billing cycle and validated.

See existing flags in `koku/masu/processor/__init__.py` for naming convention
(`cost-management.backend.<feature_name>`).  For flags checked from multiple
call sites, define a wrapper function in `__init__.py` (e.g.,
`is_customer_large()`) instead of inlining `is_feature_flag_enabled_by_schema()`
everywhere.

## Key rules (detail in `.claude/rules/`)

- **SQL templates** — three directories (`sql/`, `trino_sql/`, `self_hosted_sql/`).
  Shared openshift templates must stay in sync across `trino_sql/` and `self_hosted_sql/`.
  Port changes, don't copy — the SQL dialects differ.
- **API changes** — any PR adding/modifying endpoints **must** update
  `docs/specs/openapi.json`.  Check `koku/sources/openapi.json` and
  `koku/masu/openapi.json` too.
- **Migrations** — one per PR.  New columns **MUST** be nullable.
  Use multi-release strategy for zero-downtime deploys (add in release N,
  use in N+1, drop old in N+2).  Keep migration PRs separate from feature PRs.
- **Trino migrations** — external tables (S3-backed) safe to drop; managed
  tables (Glue-owned) **never drop**.  Use `migrate_trino_tables` command.
- **Partitioned tables** — Django's `on_delete` unreliable on partitioned tables.
  Use `cascade_delete()` from `koku/koku/database.py`.  Index FK columns.
- **On-prem parity** — test with both `ONPREM=True` and `ONPREM=False`
  when touching `get_sql_folder_name()`.

## When modifying...

| When you modify... | Also update... |
|--------------------|----------------|
| SQL templates in `trino_sql/openshift/` | Check `self_hosted_sql/openshift/` for counterpart |
| OCP updater (`ocp_cost_model_cost_updater.py`) | Check all 3 SQL template directories |
| `cost_models/models.py` or `rate_sync.py` | Test cost model create/update/delete end-to-end |
| API views or serializers | `docs/specs/openapi.json` |
| Environment variables | `deploy/clowdapp.yaml`, `koku/koku/settings.py`, `.env.example` |
| Celery tasks | Ensure `@celery_app.task(name=...)` matches function name (exception: legacy names for backwards compat) |
| New Unleash flag | `koku/masu/processor/__init__.py` (constant); `koku/koku/feature_flags.py` only if on-prem default needed |
| Provider-specific code (aws/azure/gcp/ocp) | Check other providers for parity |
| Django models (field changes) | Include migration in same or paired PR |
| New periodic Celery task | Add beat_schedule entry in `koku/koku/celery.py` |
| New Celery queue | `koku/common/queues.py` + `deploy/clowdapp.yaml` |
| New Kafka topic | `koku/kafka_utils/utils.py` constants + `deploy/clowdapp.yaml` kafkaTopics |
