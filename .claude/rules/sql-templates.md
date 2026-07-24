---
globs:
  - koku/masu/database/trino_sql/**
  - koku/masu/database/self_hosted_sql/**
---

# SQL template sync — trino_sql ↔ self_hosted_sql

Any template that exists in BOTH `trino_sql/` and `self_hosted_sql/` must
stay in sync. The SQL dialects differ (Trino vs PostgreSQL) — port changes,
don't copy.

To find the shared templates:

```bash
comm -12 \
  <(cd koku/masu/database/trino_sql && find . -name '*.sql' | sort) \
  <(cd koku/masu/database/self_hosted_sql && find . -name '*.sql' | sort)
```

Files only in `trino_sql/` are cloud-provider-specific (aws/, azure/, gcp/)
and OCP-cloud matched-tags. On-prem does not process cloud billing data.

## Third directory: masu/database/sql/

PostgreSQL templates used by DB accessors on both SaaS and on-prem.
NOT a mirror of trino_sql — but when changing cost model behavior, check
all three directories for related templates.
