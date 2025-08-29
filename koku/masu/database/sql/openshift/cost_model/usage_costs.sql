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
        node_cpu_usage,
        node_mem_usage,
        CASE WHEN {{distribution}} = 'cpu' THEN
            node_size_cpu * hours_used_cpu * {{cluster_cost_per_hour}}
        ELSE
            0
        END as node_cluster_hour_cost_cpu_per_day,
        CASE WHEN {{distribution}} = 'memory' THEN
            node_size_mem * hours_used_mem * {{cluster_cost_per_hour}}
        ELSE
            0
        END as node_cluster_hour_cost_mem_per_day
    FROM (
        SELECT
            usage_start,
            node,
            sum(pod_effective_usage_cpu_core_hours) as node_cpu_usage,
            sum(pod_effective_usage_memory_gigabyte_hours) as node_mem_usage,
            coalesce(max(node_capacity_cpu_core_hours) / nullif(max(node_capacity_cpu_cores), 0), 0) as hours_used_cpu,
            coalesce(max(node_capacity_cpu_core_hours) / nullif(max(cluster_capacity_cpu_core_hours), 0), 0) as node_size_cpu,
            coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(node_capacity_memory_gigabytes), 0), 0) as hours_used_mem,
            coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(cluster_capacity_memory_gigabyte_hours), 0), 0) as node_size_mem
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
        WHERE usage_start >= {{start_date}}
            AND usage_start <= {{end_date}}
            AND source_uuid = {{source_uuid}}
            AND node IS NOT NULL
            AND node != ''
            AND (
                cost_model_rate_type IS NULL
                OR cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
            )
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
    {{source_uuid}} as source_uuid,
    {{rate_type}} as cost_model_rate_type,
    sum(coalesce(lids.pod_usage_cpu_core_hours, 0)) * {{cpu_core_usage_per_hour}}
        + sum(coalesce(lids.pod_request_cpu_core_hours, 0)) * {{cpu_core_request_per_hour}}
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{cpu_core_effective_usage_per_hour}}
        {%- if distribution == 'cpu' %}
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{node_core_cost_per_hour}} -- (x/y) * y = x
        + sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) * {{cluster_core_cost_per_hour}}
        {%- else %}
        + sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(node_capacity_cpu_core_hours) * {{node_core_cost_per_hour}}
        + sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(node_capacity_cpu_core_hours) * {{cluster_core_cost_per_hour}}
        {%- endif %}
        + coalesce((
            sum(lids.pod_effective_usage_cpu_core_hours::decimal)
            / nullif(max(cte_node_cost.node_cpu_usage::decimal), 0)
            * max(cte_node_cost.node_cluster_hour_cost_cpu_per_day::decimal)
          ), 0)
        as cost_model_cpu_cost,
    sum(coalesce(lids.pod_usage_memory_gigabyte_hours, 0)) * {{memory_gb_usage_per_hour}}
        + sum(coalesce(lids.pod_request_memory_gigabyte_hours, 0)) * {{memory_gb_request_per_hour}}
        + sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0)) * {{memory_gb_effective_usage_per_hour}}
        + coalesce((
            sum(lids.pod_effective_usage_memory_gigabyte_hours::decimal)
            / nullif(max(cte_node_cost.node_mem_usage::decimal), 0)
            * max(cte_node_cost.node_cluster_hour_cost_mem_per_day::decimal)
          ), 0)
        as cost_model_memory_cost,
    sum(coalesce(lids.persistentvolumeclaim_usage_gigabyte_months, 0)) * {{storage_gb_usage_per_month}}
        + sum(coalesce(lids.volume_request_storage_gigabyte_months, 0)) * {{storage_gb_request_per_month}}
        as cost_model_volume_cost,
    NULL as monthly_cost_type,
    lids.cost_category_id,
    lids.all_labels
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
LEFT JOIN cte_node_cost
    ON lids.usage_start = cte_node_cost.usage_start
    AND lids.node = cte_node_cost.node
WHERE lids.usage_start >= {{start_date}}
    AND lids.usage_start <= {{end_date}}
    AND lids.source_uuid = {{source_uuid}}
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
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
