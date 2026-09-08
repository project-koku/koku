---
globs:
  - koku/masu/management/commands/migrate_trino_tables.py
  - deploy/clowdapp.yaml
---

# Trino migrations

Trino tables come in two types — handle them differently:

| Type | Data location | Safe to drop? | Identified by |
|------|--------------|---------------|---------------|
| **External** | S3/Minio (`external_location` in DDL) | Yes — only metadata lost, data stays in S3 | `SHOW CREATE TABLE` shows `external_location` |
| **Managed** | Owned by AWS Glue | **NO — dropping = data loss** | No `external_location` in DDL |

## Rules

- Managed table changes must be column add/drop only.  Never drop a
  managed table.
- Use the `migrate_trino_tables` management command for all Trino schema
  changes.  It has built-in safeguards.
- New tables must be registered in `EXTERNAL_TABLES` or `MANAGED_TABLES`
  in `koku/masu/management/commands/migrate_trino_tables.py`.
- Test locally with: `DJANGO_READ_DOT_ENV_FILE=True TRINO_HOST=localhost koku/manage.py migrate_trino_tables --help`
- In prod/stage, Trino migrations run via a ClowdJobInvocation
  (`MGMT_IMAGE_TAG`, `MGMT_INVOCATION`, `MGMT_COMMAND` in
  app-interface deploy-clowder.yml).
