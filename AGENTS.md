# Koku Ecosystem – AI Agent Guide

Slim always-on index. Load deeper docs only when the task needs them.
Always-on companion: [`CLAUDE.md`](CLAUDE.md) — dev commands, project layout, PR workflow,
feature flags, change checklists.

Follow precisely: never take shortcuts, never weaken assertions, never skip steps to make tests pass.

> **Versions:** Check `Pipfile`, `go.mod`, and `package.json` — do not rely on version numbers in docs.

---

## Quick Reference

Agent-specific defaults below. Dev stack, project layout, and commands: [`CLAUDE.md`](CLAUDE.md).

**Test schema:** `org1234567` | **Test account:** `10001` | **Test org_id:** `1234567`

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

**SQL templates / dual paths** — [`.cursor/rules/onprem-vs-saas.mdc`](.cursor/rules/onprem-vs-saas.mdc),
[`.cursor/rules/sql-templates.mdc`](.cursor/rules/sql-templates.mdc), [`CLAUDE.md`](CLAUDE.md) Key rules.

---

## Critical Constraints

1. **Dual execution paths** — cloud (Trino + PostgreSQL) and on-prem (PostgreSQL only). See on-prem vs SaaS links above and [`CLAUDE.md`](CLAUDE.md).
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

**PR workflow and commits:** [`CLAUDE.md`](CLAUDE.md).

---

## On-Demand Docs

Full catalog: [`docs/agent/README.md`](docs/agent/README.md). Use the **Task Router** above first; load docs only when the task needs them.

**Sibling repos** (read each repo's docs when working there):
- [koku-ui](https://github.com/project-koku/koku-ui)
- [koku-metrics-operator](https://github.com/project-koku/koku-metrics-operator) — operator ↔ koku integration
- [nise](https://github.com/project-koku/nise)
