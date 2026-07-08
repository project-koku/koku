---
globs:
  - koku/masu/database/trino_sql/**
  - koku/masu/database/self_hosted_sql/**
---

# SQL template sync — trino_sql ↔ self_hosted_sql

These 13 openshift templates exist in BOTH directories and must stay in sync.
The SQL dialects differ (Trino vs PostgreSQL) — port changes, don't copy.

## Shared templates (must mirror)

```
openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql
openshift/cost_model/hourly_cost_virtual_machine.sql
openshift/cost_model/hourly_cost_vm_tag_based.sql
openshift/cost_model/hourly_vm_core.sql
openshift/cost_model/hourly_vm_core_tag_based.sql
openshift/cost_model/monthly_cost_gpu.sql
openshift/cost_model/monthly_project_tag_based.sql
openshift/cost_model/monthly_vm_core.sql
openshift/cost_model/monthly_vm_core_tag_based.sql
openshift/populate_vm_tmp_table.sql
openshift/populate_vm_tmp_table_with_vm_report.sql
openshift/reporting_ocpusagelineitem_daily_summary.sql
openshift/ui_summary/reporting_ocp_gpu_summary_p_usage_only.sql
```

## Not shared (trino_sql only)

The 52 files that exist only in `trino_sql/` are cloud-provider-specific
(aws/, azure/, gcp/) and OCP-cloud matched-tags files. On-prem does not
process cloud billing data.

## Third directory: masu/database/sql/

103 PostgreSQL templates used by DB accessors on both SaaS and on-prem.
NOT a mirror of trino_sql — but when changing cost model behavior, check
all three directories for related templates.
