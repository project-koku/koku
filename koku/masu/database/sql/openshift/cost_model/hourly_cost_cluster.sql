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
    source_uuid,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_category_id
)

WITH cte_distribution_type as (
    -- get the distribution type from the cost model associated with this source
    SELECT
        {{source_uuid}} as source_uuid,
        coalesce(max(nullif(distribution_info->>'distribution_type', 'false')), 'cpu') as dt -- coalesce(max()) to return 'cpu' if a cost model does not exist for source
    FROM {{schema | sqlsafe}}.cost_model_map as cmm
    JOIN {{schema | sqlsafe}}.cost_model as cm
        ON cmm.cost_model_id = cm.uuid
    WHERE cmm.provider_uuid = {{source_uuid}}
),
cte_node_cost as (
    -- get the total cpu/mem usage of a node
    SELECT
        usage_start,
        node,
        cpu_usage,
        mem_usage,
        {{source_uuid}} as source_uuid,
        node_size_cpu * {{cluster_cost_per_hour}}::decimal(24, 9) * hours_used_cpu as node_cpu_per_day,
        node_size_mem * {{cluster_cost_per_hour}}::decimal(24, 9) * hours_used_mem as node_mem_per_day
    FROM (
        SELECT
            usage_start,
            node,
            sum(pod_effective_usage_cpu_core_hours) as cpu_usage,
            sum(pod_effective_usage_memory_gigabyte_hours) as mem_usage,
            max(node_capacity_cpu_core_hours) / max(node_capacity_cpu_cores) as hours_used_cpu,
            max(node_capacity_cpu_core_hours) / max(cluster_capacity_cpu_core_hours) as node_size_cpu,
            max(node_capacity_memory_gigabyte_hours) / max(node_capacity_memory_gigabytes) as hours_used_mem,
            max(node_capacity_memory_gigabyte_hours) / max(cluster_capacity_memory_gigabyte_hours) as node_size_mem
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
        WHERE usage_start >= {{start_date}}
            AND usage_start <= {{end_date}}
            AND source_uuid = {{source_uuid}}
        GROUP BY usage_start, node
    )
)
SELECT uuid_generate_v4() as uuid,
    {{report_period_id}} as report_period_id,
    lids.cluster_id,
    max(lids.cluster_alias) as cluster_alias,
    lids.data_source,
    lids.usage_start,
    max(lids.usage_end) as usage_end,
    lids.namespace,
    lids.node,
    lids.resource_id,
    lids.pod_labels,
    lids.pod_labels as all_labels,
    lids.source_uuid,
    {{rate_type}} as cost_model_rate_type,
    CASE WHEN cte_distribution_type.dt = 'cpu'
        THEN ( max(cte_node_cost.node_cpu_per_day) * sum(lids.pod_effective_usage_cpu_core_hours)/sum(cte_node_cost.cpu_usage) )
        ELSE 0
    END as cost_model_cpu_cost,
    CASE WHEN cte_distribution_type.dt = 'memory'
        THEN ( max(cte_node_cost.node_mem_per_day) * sum(lids.pod_effective_usage_memory_gigabyte_hours)/sum(cte_node_cost.mem_usage) )
        ELSE 0
    END as cost_model_memory_cost,
    0 as cost_model_volume_cost,
    lids.cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
JOIN cte_distribution_type
    ON lids.source_uuid = cte_distribution_type.source_uuid
JOIN cte_node_cost
    ON lids.usage_start = cte_node_cost.usage_start
    AND lids.node = cte_node_cost.node
    AND lids.source_uuid = {{source_uuid}}
WHERE lids.usage_start >= {{start_date}}
    AND lids.usage_start <= {{end_date}}
    AND lids.source_uuid = {{source_uuid}}
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.monthly_cost_type IS NULL
    AND lids.pod_effective_usage_cpu_core_hours > 0
GROUP BY lids.usage_start,
         lids.cluster_id,
         lids.source_uuid,
         lids.namespace,
         lids.node,
         lids.resource_id,
         lids.data_source,
         lids.cost_category_id,
         lids.pod_labels,
         cte_distribution_type.dt
;
