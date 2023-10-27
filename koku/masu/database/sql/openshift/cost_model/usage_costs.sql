DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = {{rate_type}}
    AND lids.monthly_cost_type IS NULL
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
    cost_category_id,
    all_labels
)
SELECT uuid_generate_v4(),
    max(report_period_id) as report_period_id,
    cluster_id,
    max(cluster_alias) as cluster_alias,
    data_source,
    usage_start,
    max(usage_end) as usage_end,
    lids.namespace,
    node,
    max(resource_id) as resource_id,
    pod_labels,
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
    max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
    max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    max(persistentvolume) as persistentvolume,
    max(storageclass) as storageclass,
    volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    {{rate_type}} as cost_model_rate_type,
    sum(coalesce(pod_usage_cpu_core_hours, 0)) * {{cpu_usage_rate}}
        + sum(coalesce(pod_request_cpu_core_hours, 0)) * {{cpu_request_rate}}
        + sum(coalesce(pod_effective_usage_cpu_core_hours, 0)) * {{cpu_effective_rate}}
        as cost_model_cpu_cost,
    sum(coalesce(pod_usage_memory_gigabyte_hours, 0)) * {{memory_usage_rate}}
        + sum(coalesce(pod_request_memory_gigabyte_hours, 0)) * {{memory_request_rate}}
        + sum(coalesce(pod_effective_usage_memory_gigabyte_hours, 0)) * {{memory_effective_rate}}
        as cost_model_memory_cost,
    sum(coalesce(persistentvolumeclaim_usage_gigabyte_months, 0)) * {{volume_usage_rate}}
        + sum(coalesce(volume_request_storage_gigabyte_months, 0)) * {{volume_request_rate}}
        as cost_model_volume_cost,
    NULL as monthly_cost_type,
    cost_category_id,
    all_labels
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
GROUP BY usage_start,
    source_uuid,
    cluster_id,
    node,
    lids.namespace,
    data_source,
    persistentvolumeclaim,
    pod_labels,
    volume_labels,
    cost_category_id,
    all_labels
;
