---
description: "Check if trino_sql and self_hosted_sql templates are in sync"
---

# Koku SQL Check — Template Sync Verification

Compare the 13 shared SQL templates between `trino_sql/` and `self_hosted_sql/`
to find any that have diverged in intent (not literal content — the dialects differ).

## Steps

### 1. List shared templates

These 13 files must exist in both directories:

```bash
for f in \
  openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql \
  openshift/cost_model/hourly_cost_virtual_machine.sql \
  openshift/cost_model/hourly_cost_vm_tag_based.sql \
  openshift/cost_model/hourly_vm_core.sql \
  openshift/cost_model/hourly_vm_core_tag_based.sql \
  openshift/cost_model/monthly_cost_gpu.sql \
  openshift/cost_model/monthly_project_tag_based.sql \
  openshift/cost_model/monthly_vm_core.sql \
  openshift/cost_model/monthly_vm_core_tag_based.sql \
  openshift/populate_vm_tmp_table.sql \
  openshift/populate_vm_tmp_table_with_vm_report.sql \
  openshift/reporting_ocpusagelineitem_daily_summary.sql \
  openshift/ui_summary/reporting_ocp_gpu_summary_p_usage_only.sql; do

  TRINO="koku/masu/database/trino_sql/$f"
  ONPREM="koku/masu/database/self_hosted_sql/$f"

  if [ ! -f "$TRINO" ]; then
    echo "MISSING in trino_sql: $f"
  elif [ ! -f "$ONPREM" ]; then
    echo "MISSING in self_hosted_sql: $f"
  fi
done
```

### 2. Check recent changes

```bash
# Files modified in last 30 days in either directory
git log --since="30 days ago" --name-only --pretty=format: -- \
  koku/masu/database/trino_sql/ koku/masu/database/self_hosted_sql/ \
  | sort -u | grep -v '^$'
```

### 3. Compare modified dates

For any recently changed file, check if its counterpart was also changed:

```bash
for f in $(git log --since="30 days ago" --name-only --pretty=format: -- \
  koku/masu/database/trino_sql/openshift/ | sort -u | grep -v '^$'); do
  relative="${f#koku/masu/database/trino_sql/}"
  counterpart="koku/masu/database/self_hosted_sql/$relative"
  if [ -f "$counterpart" ]; then
    trino_date=$(git log -1 --format='%ai' -- "$f")
    onprem_date=$(git log -1 --format='%ai' -- "$counterpart")
    if [ "$trino_date" != "$onprem_date" ]; then
      echo "OUT OF SYNC: $relative"
      echo "  trino_sql last changed:        $trino_date"
      echo "  self_hosted_sql last changed:   $onprem_date"
    fi
  fi
done
```

### 4. Present results

Output a table:

```
| Template | trino_sql | self_hosted_sql | Status |
|----------|-----------|-----------------|--------|
```

Status: `✓ in sync` / `⚠ diverged (N days)` / `✗ missing`
