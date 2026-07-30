---
description: "Check if trino_sql and self_hosted_sql templates are in sync"
---

# Koku SQL Check — Template Sync Verification

Find all SQL templates that exist in both `trino_sql/` and `self_hosted_sql/`
and check whether they've diverged. The dialects differ (Trino vs PostgreSQL),
so compare intent, not literal content.

## Steps

### 1. Discover shared templates

```bash
# Find files that exist in both directories
comm -12 \
  <(cd koku/masu/database/trino_sql && find . -name '*.sql' | sort) \
  <(cd koku/masu/database/self_hosted_sql && find . -name '*.sql' | sort)
```

### 2. Check for recent drift

For each shared template, compare when it was last modified in each directory:

```bash
for f in $(comm -12 \
  <(cd koku/masu/database/trino_sql && find . -name '*.sql' | sort) \
  <(cd koku/masu/database/self_hosted_sql && find . -name '*.sql' | sort)); do
  trino_date=$(git log -1 --format='%ai' -- "koku/masu/database/trino_sql/$f" 2>/dev/null)
  onprem_date=$(git log -1 --format='%ai' -- "koku/masu/database/self_hosted_sql/$f" 2>/dev/null)
  if [ "$trino_date" != "$onprem_date" ]; then
    echo "DIVERGED: $f"
    echo "  trino_sql:        $trino_date"
    echo "  self_hosted_sql:   $onprem_date"
  fi
done
```

### 3. Present results

Output a table:

```
| Template | trino_sql | self_hosted_sql | Status |
|----------|-----------|-----------------|--------|
```

Status: `in sync` / `diverged (N days)` / `missing`

For any diverged templates, read both versions and summarize what differs.
