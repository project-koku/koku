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
    max(report_period_id) as report_period_id,
    cluster_id,
    max(cluster_alias) as cluster_alias,
    'Pod' as data_source,
    usage_start,
    max(usage_end) as usage_end,
    lids.namespace,
    node,
    max(resource_id) as resource_id,
    pod_labels,
    pod_labels as all_labels,
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
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    {{rate_type}} as cost_model_rate_type,
    CASE
        WHEN {{cost_type}} = 'Cluster' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(cluster_capacity_cpu_core_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node_Core_Month' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * max(node_capacity_cpu_cores) * {{rate}}::decimal
        ELSE 0
    END AS cost_model_cpu_cost,
    CASE
        WHEN {{cost_type}} = 'Cluster' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(cluster_capacity_memory_gigabyte_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node_Core_Month' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(node_capacity_cpu_cores) * {{rate}}::decimal
        ELSE 0
    END as cost_model_memory_cost,
    0 as cost_model_volume_cost,
    {{cost_type}} as monthly_cost_type,
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND namespace IS NOT NULL
    AND data_source = 'Pod'
    AND monthly_cost_type IS NULL
    AND node_capacity_cpu_core_hours IS NOT NULL
    AND node_capacity_cpu_core_hours != 0
    AND cluster_capacity_cpu_core_hours IS NOT NULL
    AND cluster_capacity_cpu_core_hours != 0
    AND (
            lids.cost_model_rate_type IS NULL
            OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
        )
GROUP BY usage_start, source_uuid, cluster_id, node, namespace, pod_labels, cost_category_id
;
