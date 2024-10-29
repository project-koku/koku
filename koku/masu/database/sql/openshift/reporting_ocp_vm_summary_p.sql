DELETE FROM {{schema | sqlsafe}}.reporting_ocp_vm_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_volume_summary_by_project_p (
    cluster_alias,
    cluster_id,
    namespace,
    node,
    vm_name,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_rate_type,
    cost_model_volume_cost,
    distributed_cost,
    pod_labels,
    pod,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    infrastructure_markup_cost,
    infrastructure_raw_cost,
    raw_currency,
    resource_ids,
    usage_end,
    usage_start,
    cost_category,
    source_uuid
)
SELECT
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Pod'
        AND namespace IS DISTINCT FROM 'Worker unallocated'
        AND namespace IS DISTINCT FROM 'Platform unallocated'
        AND namespace IS DISTINCT FROM 'Network unattributed'
        AND namespace IS DISTINCT FROM 'Storage unattributed'
    GROUP BY
;
