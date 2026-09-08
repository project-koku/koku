---
globs:
  - koku/masu/processor/**
  - koku/cost_models/**
  - koku/masu/database/sql/openshift/cost_model/**
  - koku/masu/database/trino_sql/openshift/cost_model/**
  - koku/masu/database/self_hosted_sql/openshift/cost_model/**
---

# Cost model pipeline — critical path reference

This is the most dangerous code path in koku. Changes here affect cost
calculations for all tenants. Always gate behind an Unleash flag.

## Full call chain

```
HTTP POST/PUT /api/cost-management/v1/cost-models/
  → CostModelViewSet (cost_models/view.py)
    → CostModelSerializer (cost_models/serializers.py)
      → CostModelManager (cost_models/cost_model_manager.py)
        → CostModel.objects.create() / save()
        → update_provider_uuids()
          → update_cost_model_costs.apply_async()  ← Celery task per provider
        → sync_rate_table() (cost_models/rate_sync.py)

# Async path (Celery worker, triggered by apply_async above):
update_cost_model_costs task
  → CostModelCostUpdater (masu/processor/cost_model_cost_updater.py)
    → routes to provider-specific updater
```

### OCP path (full rate + markup + distribution)

```
OCPCostModelCostUpdater.update_summary_cost_model_costs()
  for each month:
    → _load_rates()
    → if RTU enabled:
        if cost_model + effective price list:
          → _update_usage_rates_to_usage()       sql/openshift/cost_model/usage_rates/
        else:
          → _cleanup_stale_rtu_costs()
      else (legacy):
        → _update_usage_costs()
    → _update_monthly_cost()                     sql/openshift/cost_model/monthly_cost_*
    → if tag rates exist:
        → _delete_tag_usage_costs()
        → _update_tag_usage_costs()              sql/openshift/cost_model/*_tag_rates.sql
        → _update_tag_usage_default_costs()
        → _update_monthly_tag_based_cost()
        → _update_node_hour_tag_based_cost()
        → populate_tag_based_costs()             (via OCPReportDBAccessor)
      else:
        → _delete_tag_usage_costs()              (cleanup only)
    → _update_vm_usage_costs()                   trino_sql|self_hosted_sql/openshift/cost_model/hourly_*
    → if RTU enabled:
        → _aggregate_rates_to_daily_summary()    sql/openshift/cost_model/usage_rates/aggregate_*
    → _update_markup_cost()
  → distribute_costs_and_update_ui_summary()
    → populate_distributed_cost_sql()            sql/openshift/cost_model/distribute_cost/
    → populate_ui_summary_tables()
```

### AWS/Azure/GCP path (markup only)

```
{Provider}CostModelCostUpdater._update_markup_cost()
  → {Provider}ReportDBAccessor.populate_markup_cost()
  → populate_ui_summary_tables()
```

## Key files (modify any → test the whole chain)

| Step | File(s) |
|------|---------|
| API/Serializer | `cost_models/view.py`, `cost_models/serializers.py` |
| Manager | `cost_models/cost_model_manager.py` |
| Rate sync | `cost_models/rate_sync.py` |
| Models | `cost_models/models.py`, `reporting/provider/ocp/models.py` |
| Celery task | `masu/processor/tasks.py` |
| Router | `masu/processor/cost_model_cost_updater.py` |
| OCP updater | `masu/processor/ocp/ocp_cost_model_cost_updater.py` |
| DB accessors | `masu/database/ocp_report_db_accessor.py` |
| SQL (PG) | `masu/database/sql/openshift/cost_model/` (20+ templates) |
| SQL (Trino) | `masu/database/trino_sql/openshift/cost_model/` |
| SQL (on-prem) | `masu/database/self_hosted_sql/openshift/cost_model/` |

## Summary tables affected

- `reporting_ocpusagelineitem_daily_summary` (main line item table)
- `rates_to_usage` (per-rate cost rows, partitioned)
- 12+ OCP UI summary tables (`reporting_ocp_cost_summary_p`, `_by_node_p`, etc.)
- AWS/Azure/GCP: markup columns on their respective daily summary tables
