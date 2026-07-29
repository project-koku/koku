# SQL / Pipeline Index

Compact map so agents open the right files instead of scanning all three SQL trees.
Paths are under `koku/` unless noted. Dialect rules: [`.cursor/rules/sql-templates.mdc`](../../.cursor/rules/sql-templates.mdc). Dual-path rules: [`.cursor/rules/onprem-vs-saas.mdc`](../../.cursor/rules/onprem-vs-saas.mdc).

## SQL directory roles

| Dir | Mode | Role |
|-----|------|------|
| `masu/database/sql/` | Both | Shared PostgreSQL: UI summaries, tags, cost-model ops |
| `masu/database/trino_sql/` | SaaS | Trino over Parquet → daily summary / OCP-on-cloud |
| `masu/database/self_hosted_sql/` | On-prem | PostgreSQL equivalents of `trino_sql/` (OCP only) |

`ReportDBAccessorBase.get_sql_folder_name()` → `self_hosted_sql` if `ONPREM` else `trino_sql`.

**Parity rule:** edits under `trino_sql/openshift/` usually need a port in `self_hosted_sql/openshift/` (do not blind-copy; dialects differ). Cloud providers (AWS/Azure/GCP) have no on-prem SQL tree.

## Provider → code + SQL roots

| Provider | Accessor | Summary updater | Cost-model updater | SQL roots |
|----------|----------|-----------------|--------------------|-----------|
| OCP | `masu/database/ocp_report_db_accessor.py` | `masu/processor/ocp/ocp_report_parquet_summary_updater.py` | `masu/processor/ocp/ocp_cost_model_cost_updater.py` | `sql/openshift/`, `{trino\|self_hosted}_sql/openshift/` |
| AWS | `masu/database/aws_report_db_accessor.py` | `masu/processor/aws/aws_report_parquet_summary_updater.py` | `masu/processor/aws/aws_cost_model_cost_updater.py` | `sql/aws/`, `trino_sql/aws/` |
| Azure | `masu/database/azure_report_db_accessor.py` | `masu/processor/azure/azure_report_parquet_summary_updater.py` | `masu/processor/azure/azure_cost_model_cost_updater.py` | `sql/azure/`, `trino_sql/azure/` |
| GCP | `masu/database/gcp_report_db_accessor.py` | `masu/processor/gcp/gcp_report_parquet_summary_updater.py` | `masu/processor/gcp/gcp_cost_model_cost_updater.py` | `sql/gcp/`, `trino_sql/gcp/` |
| OCP-on-cloud | (cloud + OCP accessors) | `masu/processor/ocp/ocp_cloud_parquet_summary_updater.py` | (via OCP/cloud updaters) | `trino_sql/{aws\|azure\|gcp}/openshift/` |

Orchestration: `masu/processor/orchestrator.py`, `masu/processor/report_summary_updater.py`, `masu/processor/cost_model_cost_updater.py`, `masu/processor/tasks.py`.

## Task → start here (read these first)

| Task | Start files |
|------|-------------|
| OCP daily summary | Accessor method using `reporting_ocpusagelineitem_daily_summary.sql` → `{trino\|self_hosted}_sql/openshift/reporting_ocpusagelineitem_daily_summary.sql` |
| OCP cost-model rates | `ocp_cost_model_cost_updater.py` → `sql/openshift/cost_model/` (shared) + `{trino\|self_hosted}_sql/openshift/cost_model/` |
| OCP cost distribution | `sql/openshift/cost_model/distribute_cost/` and `{trino\|self_hosted}_sql/openshift/cost_model/distribute_cost/` |
| OCP UI summary tables | `sql/openshift/ui_summary/` (+ `{trino\|self_hosted}_sql/openshift/ui_summary/` when mode-specific) |
| Cloud daily summary | `{aws\|azure\|gcp}_report_db_accessor.py` → `trino_sql/{provider}/reporting_*costentrylineitem_daily_summary.sql` |
| OCP-on-cloud daily | `trino_sql/{aws\|azure\|gcp}/openshift/populate_daily_summary/` + `ui_summary/` |
| Feature flags / risky SQL | `masu/processor/__init__.py` + [`CLAUDE.md`](../../CLAUDE.md) feature-flag section |
| Celery entrypoints | `masu/processor/tasks.py`, `masu/celery/tasks.py`, `koku/celery.py` beat schedule |
| Self-hosted models | `reporting/provider/ocp/self_hosted_models.py` |

## Hot SQL paths (relative to `masu/database/`)

```
# OCP daily (parallel: trino_sql ↔ self_hosted_sql)
{trino_sql|self_hosted_sql}/openshift/reporting_ocpusagelineitem_daily_summary.sql
{trino_sql|self_hosted_sql}/openshift/ui_summary/
{trino_sql|self_hosted_sql}/openshift/cost_model/          # VM/GPU/tag rates (mode-specific)
{trino_sql|self_hosted_sql}/openshift/cost_model/distribute_cost/

# OCP shared PostgreSQL (both modes)
sql/openshift/cost_model/                 # monthly/tag/usage rates, deletes
sql/openshift/cost_model/distribute_cost/
sql/openshift/ui_summary/
sql/openshift/all/ui_summary/             # all-sources UI rollups

# Cloud (SaaS / trino_sql only)
trino_sql/{aws|azure|gcp}/reporting_*costentrylineitem_daily_summary.sql
trino_sql/{aws|azure|gcp}/openshift/      # OCP-on-cloud + provider map / matched tags
sql/{aws|azure|gcp}/ui_summary/           # shared PG UI summaries
```

## Cheap lookups (avoid loading whole files)

```bash
# Find which accessor loads a template
rg -n "reporting_ocpusagelineitem_daily_summary" koku/masu/database/

# List parallel OCP templates missing in self_hosted
diff <(cd koku/masu/database/trino_sql/openshift && find . -name '*.sql' | sort) \
     <(cd koku/masu/database/self_hosted_sql/openshift && find . -name '*.sql' | sort)

# OpenAPI path snippet (files are index-ignored; extract, don't Read whole JSON)
jq '.paths | keys[]' docs/specs/openapi.json | rg -i 'cost-model'
jq '.paths["/api/cost-management/v1/cost-models/"]' docs/specs/openapi.json
```

## Related docs

- Cost-model design: [`docs/architecture/cost-models.md`](../architecture/cost-models.md)
- Celery / pipeline: [`docs/architecture/celery-tasks.md`](../architecture/celery-tasks.md)
- Ingestion: [`docs/architecture/sources-and-data-ingestion.md`](../architecture/sources-and-data-ingestion.md)
