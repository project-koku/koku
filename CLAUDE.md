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

**Commit messages:** imperative mood; first line under 72 characters; reference
Jira/GitHub issue when known (e.g. `COST-1234: Add MIG slice support`).

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
   and `/koku-release` ([`.claude/commands/koku-release.md`](.claude/commands/koku-release.md)).
6. Run `pre-commit run --all-files` before pushing.  Also run gitleaks
   with Red Hat patterns: `pre-commit run --config ~/.config/pre-commit/config.yaml`.

## Feature flags (Unleash) — gate risky changes

Agent guide (naming, UI stickiness, CI):
[`docs/agent/unleash-flags.md`](docs/agent/unleash-flags.md).

Gate risky pipeline/SQL/data-path changes behind an **enablement** flag
(`cost-management.backend.<feature>`): ON = new path, default OFF in stage/prod.
Use `dev_fallback=True` for local/dev. Do **not** use `disable-*` for feature
rollout (ops kill-switches only). Define constants in
`koku/masu/processor/__init__.py`. Keep the legacy path until the flag has been
ON in production for at least one billing cycle.

API-only additive changes may skip a flag. Details load on demand from the agent
guide (and scoped `.cursor/rules` / `.claude/rules` when editing flag code).

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
| New Unleash flag | `koku/masu/processor/__init__.py` (constant); `koku/koku/feature_flags.py` only if on-prem default needed; follow [`docs/agent/unleash-flags.md`](docs/agent/unleash-flags.md) |
| Provider-specific code (aws/azure/gcp/ocp) | Check other providers for parity |
| Django models (field changes) | Include migration in same or paired PR |
| New periodic Celery task | Add beat_schedule entry in `koku/koku/celery.py` |
| New Celery queue | `koku/common/queues.py` + `deploy/clowdapp.yaml` |
| New Kafka topic | `koku/kafka_utils/utils.py` constants + `deploy/clowdapp.yaml` kafkaTopics |
