---
globs:
  - koku/reporting/migrations/**
  - koku/cost_models/migrations/**
---

# Migrations — detailed rules

## Multi-release strategy (required for zero-downtime deploys)

All migrations must be additive — running them must not break the
currently-deployed code.

| Operation | Release N | Release N+1 | Release N+2 |
|-----------|-----------|-------------|-------------|
| **Add column** | Migration: add column (**MUST be nullable**) | Code uses the column; migration to backfill if needed | — |
| **Drop column** | Code stops using column (incl. model changes) | Migration to drop column | — |
| **Change type** | Migration: add new column with temp name | Code uses new column; migration to swap/backfill | Migration: drop old column |
| **Add table** | Migration: create table | Code uses table | — |
| **Drop table** | Code stops using table | Migration: drop table | — |

## Key rules

- New columns **MUST** be nullable or have a constant default
  (e.g., `BooleanField(default=True)` — PG 11+ stores it in metadata,
  no table rewrite).  Volatile defaults (`uuid_generate_v4()`) still
  require nullable.
- If a new column needs a default from code, the code change must deploy
  **before** the migration runs.
- Django `makemigrations` output almost always needs manual editing —
  it won't generate safe multi-release migrations on its own.
- Migrations should detect if changes have already been applied and
  handle that case gracefully.
- Prefer **one migration per PR** for easier rollback.
- Migrations adding indexes to large or partitioned tables should use
  `CREATE INDEX CONCURRENTLY` via `RunSQL` with `atomic = False`.
- New `reporting` migrations continue from the current highest number.
  Declare `cost_models` migration dependencies if touching cost_models FKs.
- Keep migration PRs separate from feature code PRs when possible.
