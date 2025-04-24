# What Are Cost Models?

Configuring a cost model allows users to associate prices to metrics and usage, and fine-tune the costs of running their cloud. This is an essential piece of running OpenShift on Prem, because without a cost model we can't generate any costs. Therefore, a majority of the features available for the cost models are related to OCP sources. However, you can still apply a markup or discount through cost models to our cloud providers (AWS, Azure, GCP).


Helpful Links:
1. Cost Managements Docs:
- https://access.redhat.com/documentation/en-us/cost_management_service/2023/html-single/using_cost_models/index


# OCP Cost Model Features:

## Price List
A price list is a mapping used to associate prices to metrics and usage. We use this mapping on the backend to calculate additional costs.

[Example](https://github.com/project-koku/koku/blob/main/dev/scripts/cost_models/openshift_on_prem_cost_model.json)

1. Price list
    - usage metrics
    - monthly rates

### Usage Metrics

The following usage metrics use a simple equation of `usage * rate` to populate an additional cost in the database:

*cost_model_cpu_cost*
1. `cpu_core_usage_per_hour`
2. `cpu_core_request_per_hour`
3. `cpu_core_effective_usage_per_hour`

*cost_model_memory_cost*
1. `memory_gb_usage_per_hour`
2. `memory_gb_request_per_hour`
3. `memory_gb_effective_usage_per_hour`

*cost_model_volume_cost*
1. `storage_gb_usage_per_month`
2. `storage_gb_request_per_month`

These metrics are multipled by the rate then aggregated to create the corresponding `cost_model_{type}_cost` column in the [usage_costs.sql](https://github.com/project-koku/koku/blob/main/koku/masu/database/sql/openshift/cost_model/usage_costs.sql) file.

After these columns are populated in the database, they are added to the overall cost in the [provider map](https://github.com/project-koku/koku/blob/main/koku/api/report/ocp/provider_map.py) to generate the user facing cost.


### Monthly Rates
Monthly rates are flat rates that are intended to cover a subscription cost.

**Cluster and Node**
These cost are amortized, which means we distribute that cost evenly throughout the month so that each day has an equal portion of the total cost for the month. We distribute the rates applied to the node & cluster metrics within the [monthly_cost_cluster_and_node.sql](https://github.com/project-koku/koku/blob/main/koku/masu/database/sql/openshift/cost_model/monthly_cost_cluster_and_node.sql).

`node_core_cost_per_month`
`node_cost_per_month`
`cluster_cost_per_month`

using the following equation:
```
effective_usage / capacity * monthly_rate
```

These costs are also inserted into the `cost_model_cpu_cost` and `cost_model_memory_cost`; however, we insert a value into the `monthly_cost_type` column to distinguish these values.

*cluster_cost_per_month*
```
select * from reporting_ocpusagelineitem_daily_summary where monthly_cost_type='Cluster';
```

*node_cost_per_month*
```
select * from reporting_ocpusagelineitem_daily_summary where monthly_cost_type='Node';
```

*node_core_cost_per_month*
```
select * from reporting_ocpusagelineitem_daily_summary where monthly_cost_type='Node_Core_Month';
```

**PVC**
The monthly PVC cost follows a slightly different logic, where rate is divided by the number of unique persistent volume claims within [monthly_cost_persistentvolumeclaim.sql](https://github.com/project-koku/koku/blob/main/koku/masu/database/sql/openshift/cost_model/monthly_cost_persistentvolumeclaim.sql).

Equation:
```
rate / pvc_count
```
*pvc_cost_per_month*
```
select * from reporting_ocpusagelineitem_daily_summary where monthly_cost_type='Node';
```
