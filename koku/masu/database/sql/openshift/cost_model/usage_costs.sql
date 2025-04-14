DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}
    AND lids.usage_start <= {{end_date}}
    AND lids.source_uuid = {{source_uuid}}
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
WITH cte_node_cost as (
    -- get the total cpu/mem usage of a node
    SELECT
        usage_start,
        node,
        cpu_usage,
        mem_usage,
        node_size_cpu * {{cluster_hour_rate}} * hours_used_cpu * cpu_distribution as node_cpu_per_day,
        node_size_mem * {{cluster_hour_rate}} * hours_used_mem * mem_distribution as node_mem_per_day
    FROM (
        SELECT
            usage_start,
            node,
            sum(pod_effective_usage_cpu_core_hours) as cpu_usage,
            sum(pod_effective_usage_memory_gigabyte_hours) as mem_usage,
            max(node_capacity_cpu_core_hours) / max(node_capacity_cpu_cores) as hours_used_cpu,
            max(node_capacity_cpu_core_hours) / max(cluster_capacity_cpu_core_hours) as node_size_cpu,
            max(node_capacity_memory_gigabyte_hours) / max(node_capacity_memory_gigabytes) as hours_used_mem,
            max(node_capacity_memory_gigabyte_hours) / max(cluster_capacity_memory_gigabyte_hours) as node_size_mem,
            CASE WHEN {{distribution}} = 'cpu' THEN 1 ELSE 0 END as cpu_distribution,
            CASE WHEN {{distribution}} = 'memory' THEN 1 ELSE 0 END as mem_distribution
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
        WHERE usage_start >= {{start_date}}
            AND usage_start <= {{end_date}}
            AND source_uuid = {{source_uuid}}
        GROUP BY usage_start, node
    )
)
SELECT uuid_generate_v4(),
    {{report_period_id}} as report_period_id,
    lids.cluster_id,
    max(lids.cluster_alias) as cluster_alias,
    lids.data_source,
    lids.usage_start,
    max(lids.usage_end) as usage_end,
    lids.namespace,
    lids.node,
    max(lids.resource_id) as resource_id,
    lids.pod_labels,
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    max(lids.node_capacity_cpu_cores) as node_capacity_cpu_cores,
    max(lids.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(lids.node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
    max(lids.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(lids.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(lids.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    lids.persistentvolumeclaim,
    max(lids.persistentvolume) as persistentvolume,
    max(lids.storageclass) as storageclass,
    lids.volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    {{source_uuid}} as source_uuid,
    {{rate_type}} as cost_model_rate_type,
    sum(coalesce(lids.pod_usage_cpu_core_hours, 0)) * {{cpu_usage_rate}}
        + sum(coalesce(lids.pod_request_cpu_core_hours, 0)) * {{cpu_request_rate}}
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{cpu_effective_rate}}
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{node_core_hour_rate}}
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{cluster_core_hour_rate}}
        + (sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0))/sum(cte_node_cost.cpu_usage) * max(cte_node_cost.node_cpu_per_day))
        as cost_model_cpu_cost,
    sum(coalesce(lids.pod_usage_memory_gigabyte_hours, 0)) * {{memory_usage_rate}}
        + sum(coalesce(lids.pod_request_memory_gigabyte_hours, 0)) * {{memory_request_rate}}
        + sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0)) * {{memory_effective_rate}}
        + (sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0))/sum(cte_node_cost.mem_usage) * max(cte_node_cost.node_mem_per_day))
        as cost_model_memory_cost,
    sum(coalesce(lids.persistentvolumeclaim_usage_gigabyte_months, 0)) * {{volume_usage_rate}}
        + sum(coalesce(lids.volume_request_storage_gigabyte_months, 0)) * {{volume_request_rate}}
        as cost_model_volume_cost,
    NULL as monthly_cost_type,
    lids.cost_category_id,
    lids.all_labels
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_node_cost
    ON lids.usage_start = cte_node_cost.usage_start
    AND lids.node = cte_node_cost.node
WHERE lids.usage_start >= {{start_date}}
    AND lids.usage_start <= {{end_date}}
    AND lids.source_uuid = {{source_uuid}}
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
GROUP BY lids.usage_start,
    lids.cluster_id,
    lids.node,
    lids.namespace,
    lids.data_source,
    lids.persistentvolumeclaim,
    lids.pod_labels,
    lids.volume_labels,
    lids.cost_category_id,
    lids.all_labels
;
