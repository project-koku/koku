DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = {{rate_type}}
    AND lids.monthly_cost_type IS NULL
    AND lids.pod_labels ? 'vm_kubevirt_io_name'
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels,
    all_labels,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
)

SELECT uuid_generate_v4(),
    max(report_period_id) AS report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    max(resource_id) AS resource_id,
    pod_labels,
    all_labels,
    max(pod_usage_cpu_core_hours) AS pod_usage_cpu_core_hours,
    max(pod_request_cpu_core_hours) AS pod_request_cpu_core_hours,
    max(pod_effective_usage_cpu_core_hours) AS pod_effective_usage_cpu_core_hours,
    max(pod_limit_cpu_core_hours) AS pod_limit_cpu_core_hours,
    max(pod_usage_memory_gigabyte_hours) AS pod_usage_memory_gigabyte_hours,
    max(pod_request_memory_gigabyte_hours) AS pod_request_memory_gigabyte_hours,
    max(pod_effective_usage_memory_gigabyte_hours) AS pod_effective_usage_memory_gigabyte_hours,
    max(pod_limit_memory_gigabyte_hours) AS pod_limit_memory_gigabyte_hours,
    NULL AS node_capacity_cpu_cores,
    NULL AS node_capacity_cpu_core_hours,
    NULL AS node_capacity_memory_gigabytes,
    NULL AS node_capacity_memory_gigabyte_hours,
    NULL AS cluster_capacity_cpu_core_hours,
    NULL AS cluster_capacity_memory_gigabyte_hours,
    NULL AS persistentvolumeclaim,
    NULL AS persistentvolume,
    NULL AS storageclass,
    NULL AS volume_labels,
    NULL AS persistentvolumeclaim_capacity_gigabyte,
    NULL AS persistentvolumeclaim_capacity_gigabyte_months,
    NULL AS volume_request_storage_gigabyte_months,
    NULL AS persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    24 * {{vm_cost_per_hour}}::decimal as cost_model_cpu_cost,
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    NULL AS monthly_cost_type,
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND all_labels ? 'vm_kubevirt_io_name'
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
    AND monthly_cost_type IS NULL
GROUP BY usage_start,
    usage_end,
    source_uuid,
    cluster_id,
    cluster_alias,
    node,
    namespace,
    data_source,
    cost_category_id,
    pod_labels,
    all_labels
;
