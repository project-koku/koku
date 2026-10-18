---
paths:
  - "**/migrations/*.py"
---


# Migrations — detailed rules

## Multi-release strategy (required for zero-downtime deploys)

All migrations must be additive — running them must not break the
currently-deployed code.

| Operation | Release N | Release N+1 | Release N+2 |
|-----------|-----------|-------------|-------------|
| **Add column** | Migration: add column (**nullable, or constant `db_default`**) | Code uses the column; migration to backfill if needed | — |
| **Drop column** | Code stops using column (incl. model changes) | Migration to drop column | — |
| **Change type** | Migration: add new column with temp name | Code uses new column; migration to swap/backfill | Migration: drop old column |
| **Add table** | Migration: create table | Code uses table | — |
| **Drop table** | Code stops using table | Migration: drop table | — |

## Key rules

- New columns **MUST** be nullable, or `NOT NULL` with a constant database
  default via `db_default=` (e.g., `BooleanField(default=True, db_default=True)`;
  PG 11+ stores a constant default in metadata, no table rewrite).  A Python
  `default=` alone is not enough: Django drops the database default right after
  adding the column, so inserts from the previous release (ORM and raw-SQL
  templates that don't know the column) fail on `NOT NULL`.  Volatile defaults
  (`uuid_generate_v4()`) still require nullable.
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

## Partitioned tables and running migrations

### Partitioned Tables

All partitioned tables use RANGE partitioning on `usage_start` (monthly) and have `_p` or `_P` suffix.

### Creating New Partitioned Tables

```python
migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
migrations.CreateModel(
    name="NewSummaryP",
    fields=[...],
    options={"db_table": "reporting_new_summary_p"},
),
migrations.AddIndex(model_name="newsummaryp", index=...),
migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
```

### Adding Columns to Existing Partitioned Tables

Standard `AddField` - no `set_pg_extended_mode` needed:

```python
migrations.AddField(
    model_name="ocpusagelineitemdailysummary",
    name="new_column",
    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
),
```

### Running Migrations

Migrations run with `migrate_schemas` (django-tenants multiprocessing executor):

```bash
pipenv run python koku/manage.py migrate_schemas
```

### Trino/Hive Tables

NOT managed by Django migrations. Created at runtime by masu processors.
