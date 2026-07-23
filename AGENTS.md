# Koku Ecosystem – AI Agent Guide

Slim always-on index. Load deeper docs only when the task needs them.
Follow precisely: never take shortcuts, never weaken assertions, never skip steps to make tests pass.

> **Versions:** Check `Pipfile`, `go.mod`, and `package.json` — do not rely on version numbers in docs.

---

## Quick Reference

**Test schema:** `org1234567` | **Test account:** `10001` | **Test org_id:** `1234567`

```bash
# On-prem (OCP only, faster)
ONPREM=True docker compose up -d db valkey koku-server masu-server koku-worker koku-beat

# SaaS (all providers, Trino)
make docker-up-min-trino

# Tests
pipenv run tox -- koku.masu.test.path.to.test_module
```

**Identity header (base64):**

```bash
echo -n '{"identity":{"account_number":"10001","org_id":"1234567","type":"User","user":{"username":"user_dev","email":"user_dev@foo.com","is_org_admin":true,"access":{}}},"entitlements":{"cost_management":{"is_entitled":true}}}' | base64 -w0
```

**Tenant-scoped queries** — [`.cursor/rules/multi-tenancy.mdc`](.cursor/rules/multi-tenancy.mdc):

```python
from django_tenants.utils import schema_context
with schema_context(self.schema):
    rows = OCPUsageLineItemDailySummary.objects.filter(...)
```

**SQL template directories** — [`.cursor/rules/onprem-vs-saas.mdc`](.cursor/rules/onprem-vs-saas.mdc), [`.cursor/rules/sql-templates.mdc`](.cursor/rules/sql-templates.mdc):

| Directory | Mode | Purpose |
|-----------|------|---------|
| `masu/database/sql/` | Both | UI summaries, tags, cost model ops |
| `masu/database/trino_sql/` | SaaS | Trino aggregation over Parquet |
| `masu/database/self_hosted_sql/` | On-prem | PostgreSQL parallel to `trino_sql/` |

---

## Critical Constraints

1. **Dual execution paths** — cloud (Trino + PostgreSQL) and on-prem (PostgreSQL only). SQL changes often need both `trino_sql/` and `self_hosted_sql/`.
2. **Multi-tenancy** — `reporting` and `cost_models` require `schema_context` / `tenant_context`. Public models (`api`, `sources`) do not.
3. **OCI removed** — do not implement OCI support.
4. **Feature flags** — gate risky pipeline/SQL changes only when required ([`CLAUDE.md`](CLAUDE.md)).
5. **Providers:** AWS, Azure, GCP, OpenShift (+ OCP-on-cloud variants).

**Required test mocks** (patch at import location) — full detail in [`docs/agent/testing.md`](docs/agent/testing.md):

| Service | Patch target | Return |
|---------|--------------|--------|
| Trino | `masu.database.ocp_report_db_accessor.trino_table_exists` | `False` |
| Trino | `...OCPReportDBAccessor.schema_exists_trino` | `False` |
| Unleash | `...is_feature_flag_enabled_by_schema` | `False` |
| Currency | `api.report.serializers.get_currency` | `"USD"` |

---

## Task Router

Load the doc or rule **before** editing when the task matches:

| If you are... | Load |
|---------------|------|
| Editing `*.sql` templates | [`.cursor/rules/sql-templates.mdc`](.cursor/rules/sql-templates.mdc) |
| Changing masu pipeline / accessors / Celery | [`.cursor/rules/onprem-vs-saas.mdc`](.cursor/rules/onprem-vs-saas.mdc), [`docs/architecture/celery-tasks.md`](docs/architecture/celery-tasks.md) |
| Changing report API / `provider_map.py` | [`.cursor/rules/provider-maps.mdc`](.cursor/rules/provider-maps.mdc), [`.cursor/rules/onprem-vs-saas.mdc`](.cursor/rules/onprem-vs-saas.mdc), [`docs/architecture/api-serializers-provider-maps.md`](docs/architecture/api-serializers-provider-maps.md) |
| Writing or fixing tests | [`docs/agent/testing.md`](docs/agent/testing.md), [`.cursor/rules/testing-patterns.mdc`](.cursor/rules/testing-patterns.mdc) |
| Django ORM / aggregations / date helpers | [`docs/agent/backend-gotchas.md`](docs/agent/backend-gotchas.md) |
| Local stack / nise / UI E2E | [`docs/local-development.md`](docs/local-development.md) |
| Cost model SQL or distribution | [`docs/architecture/cost-models.md`](docs/architecture/cost-models.md) |
| PRD → design docs | [`docs/architecture/README.md`](docs/architecture/README.md), `/architect` command |

---

## Agent Behavior

**Ask first when:** >5 files or multiple subsystems; ambiguous business logic; major refactors; test failure may indicate wrong expected behavior.

**Proceed when:** Scoped, well-defined task; clear bug fix; established pattern.

**Never:** `try/except: pass` or `self.skipTest()` to green tests; weaken assertions; silent `continue` in loops; bogus mock data when testing real behavior.

**Always:** Fix root causes; mock at import location; read production code before changing tests/SQL; verify DB state before changing assertions.

**PR titles:** `[ISSUE_KEY] Short description` or description only if no issue key.

**Commits:** imperative mood, first line under 72 chars; reference issue when known
(e.g. `COST-1234: Add MIG slice support`). PR workflow and feature flags: [`CLAUDE.md`](CLAUDE.md).

---

## On-Demand Docs

Full catalog: [`docs/agent/README.md`](docs/agent/README.md). Use the **Task Router** above first; load docs only when the task needs them.

**Sibling repos** (read each repo's docs when working there):
- [koku-ui](https://github.com/project-koku/koku-ui)
- [koku-metrics-operator](https://github.com/project-koku/koku-metrics-operator) — operator ↔ koku integration
- [nise](https://github.com/project-koku/nise)
