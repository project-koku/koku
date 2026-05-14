DELETE FROM {{schema | sqlsafe}}.reporting_ocp_pod_summary_by_node_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

WITH line_items AS (
    SELECT
        cluster_id,
        cluster_alias,
        node,
        resource_id,
        usage_start,
        cost_model_rate_type,
        infrastructure_raw_cost,
        infrastructure_markup_cost,
        cost_model_cpu_cost,
        cost_model_memory_cost,
        cost_model_volume_cost,
        cost_model_gpu_cost,
        pod_usage_cpu_core_hours,
        pod_request_cpu_core_hours,
        pod_effective_usage_cpu_core_hours,
        pod_limit_cpu_core_hours,
        pod_usage_memory_gigabyte_hours,
        pod_request_memory_gigabyte_hours,
        pod_effective_usage_memory_gigabyte_hours,
        pod_limit_memory_gigabyte_hours,
        cluster_capacity_cpu_core_hours,
        cluster_capacity_memory_gigabyte_hours,
        node_capacity_cpu_cores,
        node_capacity_cpu_core_hours,
        node_capacity_memory_gigabytes,
        node_capacity_memory_gigabyte_hours,
        cost_category_id,
        raw_currency,
        distributed_cost,
        data_source,
        -- Window: sums from base rows (rate_type IS NULL) at node+cluster+date level.
        -- Enables cross-rate-type waste computation in the outer SELECT.
        SUM(CASE WHEN cost_model_rate_type IS NULL THEN COALESCE(pod_usage_cpu_core_hours, 0) ELSE 0 END)
            OVER (PARTITION BY cluster_id, node, usage_start) AS grp_cpu_usage,
        SUM(CASE WHEN cost_model_rate_type IS NULL THEN COALESCE(pod_effective_usage_cpu_core_hours, 0) ELSE 0 END)
            OVER (PARTITION BY cluster_id, node, usage_start) AS grp_cpu_effective,
        SUM(CASE WHEN cost_model_rate_type IS NULL THEN COALESCE(pod_usage_memory_gigabyte_hours, 0) ELSE 0 END)
            OVER (PARTITION BY cluster_id, node, usage_start) AS grp_mem_usage,
        SUM(CASE WHEN cost_model_rate_type IS NULL THEN COALESCE(pod_effective_usage_memory_gigabyte_hours, 0) ELSE 0 END)
            OVER (PARTITION BY cluster_id, node, usage_start) AS grp_mem_effective
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Pod'
        AND namespace IS DISTINCT FROM 'Worker unallocated'
        AND namespace IS DISTINCT FROM 'Platform unallocated'
        AND namespace IS DISTINCT FROM 'Network unattributed'
        and namespace IS DISTINCT FROM 'Storage unattributed'
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_pod_summary_by_node_p (
    id,
    cluster_id,
    cluster_alias,
    node,
    resource_ids,
    resource_count,
    data_source,
    usage_start,
    usage_end,
    infrastructure_raw_cost,
    infrastructure_markup_cost,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_gpu_cost,
    cost_model_rate_type,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    source_uuid,
    cost_category_id,
    raw_currency,
    distributed_cost,
    wasted_cpu_cost,
    wasted_memory_cost
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        node,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        max(data_source) as data_source,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        sum(cost_model_gpu_cost) as cost_model_gpu_cost,
        cost_model_rate_type,
        sum(pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
        sum(pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
        sum(pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
        sum(pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
        sum(pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
        sum(pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
        sum(pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
        sum(pod_limit_memory_gigabyte_hours) as pod_limit_memory_gigabyte_hours,
        max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        {{source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id,
        max(raw_currency) as raw_currency,
        sum(distributed_cost) as distributed_cost,
        CASE
            WHEN cost_model_rate_type IN ('Infrastructure', 'Supplementary')
            THEN GREATEST(0,
                SUM(COALESCE(cost_model_cpu_cost, 0))
                * (1 - MAX(grp_cpu_usage) / NULLIF(MAX(grp_cpu_effective), 0))
            )
            ELSE 0
        END AS wasted_cpu_cost,
        CASE
            WHEN cost_model_rate_type IN ('Infrastructure', 'Supplementary')
            THEN GREATEST(0,
                SUM(COALESCE(cost_model_memory_cost, 0))
                * (1 - MAX(grp_mem_usage) / NULLIF(MAX(grp_mem_effective), 0))
            )
            ELSE 0
        END AS wasted_memory_cost
    FROM line_items
    GROUP BY usage_start, cluster_id, cluster_alias, node, cost_model_rate_type
;
