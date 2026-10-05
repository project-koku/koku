# Koku – agent guide

The single always-on instruction file for every coding agent working in this
repository. Topic guides in [`docs/agent/`](docs/agent/README.md) load on
demand: Claude Code and Cursor attach them automatically when you work on
matching files, and the **Task Router** below lists them for every other agent.
How that wiring works: [`docs/agent/README.md`](docs/agent/README.md).

> **Versions:** Check [`Pipfile`](Pipfile) — do not rely on version numbers in docs.

## Quick reference

**Key commands:**
```
make docker-up-min          # start dev stack (PG, Valkey, S4, Trino, Unleash, workers)
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

**Tests:** schema `org1234567`, account `10001`, org_id `1234567`. Running and
writing tests: [`docs/agent/testing.md`](docs/agent/testing.md).

```python
from django_tenants.utils import schema_context
with schema_context(self.schema):
    rows = OCPUsageLineItemDailySummary.objects.filter(...)
```

## PR workflow and releases

**Commit messages and PR titles:** `[COST-1234] Imperative subject` when there is a
ticket (e.g. `[COST-1234] Add MIG slice support`), otherwise a plain imperative
subject; first line under 72 characters.

1. Open PRs as **DRAFT**.  Mark **Ready for Review** when done.
2. Add `smokes-required` + `hot-fix-smoke-tests` labels (Konflux CI gate +
   IQE smoke tests).  For non-code PRs (docs, dashboards), use
   `ok-to-skip-smokes` instead.
3. Smoke tests **must pass** before merging (unless the PR only touches
   non-build files like docs).
4. Merges to `main` **auto-deploy to stage**.
5. Production releases are manual — Mon/Thu cadence via app-interface MRs.
   Use `make get-release-commit` to get the right commit hash (the commit
   before midnight UTC, so IQE has tested it). Agent-assisted flow:
   [`docs/agent/production-release.md`](docs/agent/production-release.md)
   (the `koku-release` command in Claude Code and Cursor).
6. Run `pre-commit run --all-files` before pushing.  Also run gitleaks
   with Red Hat patterns: `pre-commit run --config ~/.config/pre-commit/config.yaml`.

## Critical constraints

1. **Dual execution paths** — cloud (Trino + PostgreSQL) and on-prem (PostgreSQL only).
   Test with both `ONPREM=True` and `ONPREM=False` when touching `get_sql_folder_name()`.
   See [`docs/agent/onprem-vs-saas.md`](docs/agent/onprem-vs-saas.md).
2. **Multi-tenancy** — `reporting` and `cost_models` require `schema_context` /
   `tenant_context`. Public models (`api`, `sources`) do not. See
   [`docs/agent/multi-tenancy.md`](docs/agent/multi-tenancy.md).
3. **Feature flags (Unleash)** — gate risky pipeline/SQL/data-path changes behind an
   **enablement** flag (`cost-management.backend.<feature>`): ON = new path, default
   OFF in stage/prod. Use `dev_fallback=True` for local/dev. Do **not** use
   `disable-*` for feature rollout (ops kill-switches only). Define constants in
   `koku/masu/processor/__init__.py`. Keep the legacy path until the flag has been ON
   in production for at least one billing cycle. API-only additive changes may skip
   a flag. Details: [`docs/agent/unleash-flags.md`](docs/agent/unleash-flags.md).
4. **SQL templates** — three directories (`sql/`, `trino_sql/`, `self_hosted_sql/`).
   Shared openshift templates must stay in sync across `trino_sql/` and
   `self_hosted_sql/`. Port changes, don't copy — the SQL dialects differ.
5. **API changes** — any PR adding/modifying endpoints **must** update
   `docs/specs/openapi.json`.  Check `koku/sources/openapi.json` and
   `koku/masu/openapi.json` too.
6. **Migrations** — one per PR.  New columns **MUST** be nullable, or `NOT NULL`
   with a constant `db_default=` (a Python `default=` alone breaks the previous release's inserts).
   Use multi-release strategy for zero-downtime deploys (add in release N,
   use in N+1, drop old in N+2).  Keep migration PRs separate from feature PRs.
   See [`docs/agent/migrations.md`](docs/agent/migrations.md).
7. **Trino migrations** — external tables (S3-backed) safe to drop; managed
   tables (Glue-owned) **never drop**.  Use `migrate_trino_tables` command.
8. **Partitioned tables** — Django's `on_delete` unreliable on partitioned tables.
   Use `cascade_delete()` from `koku/koku/database.py`.  Index FK columns.
9. **OCI removed** — do not implement OCI support.
10. **Providers:** AWS, Azure, GCP, OpenShift (+ OCP-on-cloud variants).

## When modifying...

| When you modify... | Also update... |
|--------------------|----------------|
| SQL templates in `trino_sql/openshift/` | Check `self_hosted_sql/openshift/` for counterpart |
| OCP updater (`ocp_cost_model_cost_updater.py`) | Check all 3 SQL template directories |
| `cost_models/models.py` or `rate_sync.py` | Test cost model create/update/delete end-to-end |
| API views or serializers | `docs/specs/openapi.json` |
| Environment variables | `deploy/clowdapp.yaml`, `koku/koku/settings.py`, `.env.example` |
| Celery tasks | Ensure `@celery_app.task(name=...)` matches function name (exception: legacy names for backwards compat) |
| New Unleash flag | `koku/masu/processor/__init__.py` (constant); `koku/koku/feature_flags.py` only if on-prem default needed; follow [`docs/agent/unleash-flags.md`](docs/agent/unleash-flags.md) |
| Provider-specific code (aws/azure/gcp/ocp) | Check other providers for parity |
| Django models (field changes) | Include migration in same or paired PR |
| New periodic Celery task | Add beat_schedule entry in `koku/koku/celery.py` |
| New Celery queue | `koku/common/queues.py` + `deploy/clowdapp.yaml` |
| New Kafka topic | `koku/kafka_utils/utils.py` constants + `deploy/clowdapp.yaml` kafkaTopics |

## Task Router

Load the matching guide **before** editing:

| If you are... | Load |
|---------------|------|
| Editing `*.sql` templates | [`sql-templates.md`](docs/agent/sql-templates.md), [`onprem-vs-saas.md`](docs/agent/onprem-vs-saas.md) |
| Changing masu pipeline / accessors / Celery | [`onprem-vs-saas.md`](docs/agent/onprem-vs-saas.md), [`celery-tasks.md`](docs/agent/celery-tasks.md), [`docs/architecture/celery-tasks.md`](docs/architecture/celery-tasks.md) |
| Cost model pipeline or cost model SQL | [`cost-pipeline.md`](docs/agent/cost-pipeline.md), [`docs/architecture/cost-models.md`](docs/architecture/cost-models.md) |
| New pipeline feature / SQL write path | [`unleash-flags.md`](docs/agent/unleash-flags.md), [`onprem-vs-saas.md`](docs/agent/onprem-vs-saas.md) |
| Django migrations / partitioned tables | [`migrations.md`](docs/agent/migrations.md), [`partitioned-tables.md`](docs/agent/partitioned-tables.md) |
| Trino schema changes | [`trino-migrations.md`](docs/agent/trino-migrations.md) |
| Sources / Kafka / data ingestion | [`docs/architecture/sources-and-data-ingestion.md`](docs/architecture/sources-and-data-ingestion.md), [`file-processing.md`](docs/agent/file-processing.md) |
| Changing report API / `provider_map.py` | [`provider-maps.md`](docs/agent/provider-maps.md), [`api-design.md`](docs/agent/api-design.md), [`docs/architecture/api-serializers-provider-maps.md`](docs/architecture/api-serializers-provider-maps.md) |
| API / OpenAPI changes | [`api-design.md`](docs/agent/api-design.md), [`docs/specs/openapi.json`](docs/specs/openapi.json) |
| OCP report processing | [`ocp-processing.md`](docs/agent/ocp-processing.md), [`file-processing.md`](docs/agent/file-processing.md) |
| Writing or fixing tests | [`testing.md`](docs/agent/testing.md), [`write-unit-tests` playbook](docs/agent/playbooks/write-unit-tests.md) |
| Django ORM / models / accessors | [`django-db.md`](docs/agent/django-db.md), [`backend-gotchas.md`](docs/agent/backend-gotchas.md) |
| Logging | [`logging-patterns.md`](docs/agent/logging-patterns.md) |
| Python style | [`python-conventions.md`](docs/agent/python-conventions.md) |
| Domain terms (provider, source, manifest, cost model) | [`domain-context.md`](docs/agent/domain-context.md) |
| Local stack / nise / UI E2E | [`docs/local-development.md`](docs/local-development.md) |
| Querying prod/stage databases | [`database-queries` playbook](docs/agent/playbooks/database-queries.md) |
| Editing architecture docs | [`architecture-docs.md`](docs/agent/architecture-docs.md) |
| PRD → design docs | [`architect` playbook](docs/agent/playbooks/architect.md), [`docs/architecture/README.md`](docs/architecture/README.md) |
| Production release / promote to prod | [`production-release.md`](docs/agent/production-release.md) |

## Agent behavior

**Ask first when:** >5 files or multiple subsystems; ambiguous business logic; major refactors; test failure may indicate wrong expected behavior.

**Proceed when:** Scoped, well-defined task; clear bug fix; established pattern.

**Never:** `try/except: pass` or `self.skipTest()` to green tests; weaken assertions; silent `continue` in loops; bogus mock data when testing real behavior.

**Always:** Fix root causes; mock at import location; read production code before changing tests/SQL; verify DB state before changing assertions.

## On-demand docs

Full catalog, playbooks, and how per-tool wrappers map to them:
[`docs/agent/README.md`](docs/agent/README.md).
