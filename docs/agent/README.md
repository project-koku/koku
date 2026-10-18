# Agent on-demand docs

Topic guides and playbooks for coding agents. Start with the **Task Router** in
[`AGENTS.md`](../../AGENTS.md), then open entries from this catalog.

## How agent context is wired

The content lives **only here**. Tool-specific directories hold thin wrappers:

| Tool | Always on | Topic guides attached by path | Commands |
|------|-----------|-------------------------------|----------|
| Every agent | [`AGENTS.md`](../../AGENTS.md) | Task Router links | [`playbooks/`](playbooks/) |
| Claude Code | `AGENTS.md` (read natively, no `CLAUDE.md`) | `.claude/rules/<topic>.md` — symlinks to guides here; Claude Code scopes on the guide's `paths:` frontmatter | `.claude/commands/` |
| Cursor | `AGENTS.md`, `.cursor/rules/{domain-context,multi-tenancy}.mdc` | `.cursor/rules/<topic>.mdc` — `globs` frontmatter + `@docs/agent/<topic>.md` | `.cursor/commands/`, `.cursor/skills/koku-release/` |

When you change a rule, edit the guide here, not the wrapper. To make a guide
attach by path in Claude Code, give it `paths:` frontmatter and symlink it:
`ln -s ../../docs/agent/<topic>.md .claude/rules/<topic>.md` (an `@` import in a
rule file is loaded at launch, which defeats the path scoping). For Cursor, add
a `.cursor/rules/<topic>.mdc` wrapper with the patterns as `globs`.

## Topic guides

| Topic | Guide |
|-------|-------|
| Domain terms, data flow | [`domain-context.md`](domain-context.md) |
| Multi-tenancy (`schema_context` / `tenant_context`) | [`multi-tenancy.md`](multi-tenancy.md) |
| On-prem vs SaaS | [`onprem-vs-saas.md`](onprem-vs-saas.md) |
| SQL templates (sync, dialects, Jinja) | [`sql-templates.md`](sql-templates.md) |
| Cost model pipeline | [`cost-pipeline.md`](cost-pipeline.md) |
| Django migrations | [`migrations.md`](migrations.md) |
| Partitioned tables, `cascade_delete()` | [`partitioned-tables.md`](partitioned-tables.md) |
| Trino migrations | [`trino-migrations.md`](trino-migrations.md) |
| Unleash feature flags (backend) | [`unleash-flags.md`](unleash-flags.md) |
| API design, serializers, OpenAPI | [`api-design.md`](api-design.md) |
| Provider maps | [`provider-maps.md`](provider-maps.md) |
| Celery tasks and queues | [`celery-tasks.md`](celery-tasks.md) |
| Django ORM / accessors | [`django-db.md`](django-db.md) |
| Report file processing | [`file-processing.md`](file-processing.md) |
| OpenShift processing | [`ocp-processing.md`](ocp-processing.md) |
| Structured logging | [`logging-patterns.md`](logging-patterns.md) |
| Python style | [`python-conventions.md`](python-conventions.md) |
| Unit testing | [`testing.md`](testing.md) |
| Architecture doc style | [`architecture-docs.md`](architecture-docs.md) |
| Backend ORM / date helpers | [`backend-gotchas.md`](backend-gotchas.md) |
| Production release (HCCM) | [`production-release.md`](production-release.md) → scripts in [`../../dev/scripts/release/`](../../dev/scripts/release/) |
| OCP metrics operator | [`koku-metrics-operator.md`](koku-metrics-operator.md) → [repo](https://github.com/project-koku/koku-metrics-operator) |

## Playbooks

Procedures an agent runs on request; some are also exposed as commands.

| Playbook | Use when |
|----------|----------|
| [`database-queries.md`](playbooks/database-queries.md) | Read-only SQL against prod/stage via gabi-cli (Claude Code: `/koku-database`) |
| [`sql-template-sync-check.md`](playbooks/sql-template-sync-check.md) | Check whether `trino_sql/` and `self_hosted_sql/` templates diverged (Claude Code: `/koku-sql-check`) |
| [`production-release.md`](production-release.md) | Promote koku to production with approval gates (`koku-release` in Claude Code and Cursor) |
| [`architect.md`](playbooks/architect.md) | Turn a PRD into architecture docs under `docs/architecture/` (Cursor: `/architect`) |
| [`write-unit-tests.md`](playbooks/write-unit-tests.md) | Add or extend unit tests (Cursor: `/write-unit-tests`) |
| [`light-review-existing-diffs.md`](playbooks/light-review-existing-diffs.md) | Quick first-pass review of current diffs (Cursor) |
| [`code-review-checklist.md`](playbooks/code-review-checklist.md) | Thorough review before approving (Cursor) |
| [`create-pr-testing-instructions.md`](playbooks/create-pr-testing-instructions.md) | PR description in the Koku template (Cursor) |
| [`address-github-pr-comments.md`](playbooks/address-github-pr-comments.md) | Work through reviewer comments (Cursor) |

These are guidance templates, not hard rules; if one conflicts with current team
conventions, follow the conventions.

## Architecture and local development

| Topic | Doc |
|-------|-----|
| Local stack, nise, ingest, UI E2E | [`../local-development.md`](../local-development.md) |
| Env vars, dev tooling | [`../devtools.md`](../devtools.md) |
| Feature architecture | [`../architecture/README.md`](../architecture/README.md) |
| Celery tasks / pipeline | [`../architecture/celery-tasks.md`](../architecture/celery-tasks.md) |
| Sources / data ingestion | [`../architecture/sources-and-data-ingestion.md`](../architecture/sources-and-data-ingestion.md) |
| Cost models pipeline | [`../architecture/cost-models.md`](../architecture/cost-models.md) |
| API / provider maps | [`../architecture/api-serializers-provider-maps.md`](../architecture/api-serializers-provider-maps.md) |
