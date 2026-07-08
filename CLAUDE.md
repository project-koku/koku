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

**Dev stack:** PostgreSQL :15432, Redis :6379, Minio :9000, Trino :8032

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
(`cost-management.backend.<feature_name>`).

## SQL templates — three directories, sync rules

There are **three** SQL template directories:

| Directory | Engine | Scope |
|-----------|--------|-------|
| `koku/masu/database/sql/` | PostgreSQL | Primary path, both SaaS and on-prem (103 files) |
| `koku/masu/database/trino_sql/` | Trino | SaaS-only, selected when `ONPREM=False` (65 files) |
| `koku/masu/database/self_hosted_sql/` | PostgreSQL | On-prem-only, selected when `ONPREM=True` (13 files) |

`self_hosted_sql/` is a **strict subset** of `trino_sql/` — 13 shared
openshift templates that must stay in sync.  Any bug fix or behaviour change
to a template under one path must be ported (not copied — the SQL dialects
differ) to the counterpart.  When changing cost model behavior, check all
three directories.

## API changes — update OpenAPI spec

Any PR that adds or modifies API endpoints **must** include corresponding
updates to `docs/specs/openapi.json`.  Also check whether
`koku/sources/openapi.json` or `koku/masu/openapi.json` are relevant.

## Migrations

- **One migration per PR** for easier rollback.
- Migrations touching large or partitioned tables should use
  `AddIndexConcurrently` with `atomic = False`.
- New `reporting` migrations continue from the current highest number.
  Declare `cost_models` migration dependencies if touching cost_models FKs.
- Keep migration PRs separate from feature code PRs when possible.

## Partitioned tables and Django FK constraints

Django's `on_delete=SET_NULL` / `CASCADE` is handled in Python by Django's
`Collector`, NOT at the database level — the DB-level FK constraint is just
`REFERENCES ... NO ACTION DEFERRABLE INITIALLY DEFERRED`.  Django issues
UPDATE/DELETE SQL before the main DELETE, which normally works fine.

However, for **partitioned tables** (any model with a `PartitionInfo` inner class),
the deferred FK enforcement triggers in PostgreSQL can misbehave — particularly
after partition management operations (ATTACH/DETACH/trigger-based creation via
`trfn_partition_manager`).  This has caused production `IntegrityError` on
commit despite Django's Collector having already issued the SET_NULL UPDATE
(see COST-7736 / PR #6166).

**Rules when deleting objects referenced by partitioned tables:**

1. Do NOT rely on Django's `on_delete` declarations alone.  Either use the
   custom `cascade_delete()` from `koku/database.py` (which calls
   `SET CONSTRAINTS ALL IMMEDIATE` and walks relations manually), or
   explicitly null/delete referencing rows before the delete.
2. If you add a new FK from a partitioned table to a non-partitioned table,
   consider adding a database index on the FK column — without it, the
   SET_NULL UPDATE sequential-scans every partition.
3. The `rates_to_usage` table (`RatesToUsage` model) is the primary example.
   It has `SET_NULL` FKs to both `Rate` and `CostModel`.  The table is
   heavily skewed — most tenants have zero rows, but a few large tenants
   have millions.  Always index FK columns on partitioned tables.

## On-prem parity

When adding features that involve `get_sql_folder_name()`, always test with
both `ONPREM=True` and `ONPREM=False`.  On-prem SQL templates live in
`self_hosted_sql/` and must have counterparts for any template loaded via
`get_sql_folder_name()`.

## When modifying...

| When you modify... | Also update... |
|--------------------|----------------|
| SQL templates in `trino_sql/openshift/` | Check `self_hosted_sql/openshift/` for counterpart |
| OCP updater (`ocp_cost_model_cost_updater.py`) | Check all 3 SQL template directories |
| `cost_models/models.py` or `rate_sync.py` | Test cost model create/update/delete end-to-end |
| API views or serializers | `docs/specs/openapi.json` |
| Environment variables | `deploy/clowdapp.yaml`, `koku/koku/settings.py`, `.env.example` |
| Celery tasks | Ensure `@app.task(name=...)` matches function name |
| New Unleash flag | `koku/masu/processor/__init__.py` (constant), `koku/koku/feature_flags.py` (on-prem default), `dev/scripts/setup_unleash.py` |
| Provider-specific code (aws/azure/gcp/ocp) | Check other providers for parity |
| Django models (field changes) | Include migration in same or paired PR |
