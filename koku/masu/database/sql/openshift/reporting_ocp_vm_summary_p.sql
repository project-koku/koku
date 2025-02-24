DELETE FROM {{schema | sqlsafe}}.reporting_ocp_vm_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

WITH second_to_last_day AS (
    SELECT DISTINCT usage_start::date AS day
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND pod_request_cpu_core_hours IS NOT NULL
    ORDER BY day DESC
    OFFSET 1 LIMIT 1  -- Get the second-to-last day
),
cte_distribution_type AS (
    -- get the distribution type from the cost model associated with this source
    SELECT
        {{source_uuid}}::uuid as source_uuid,
        coalesce(max(cm.distribution), 'cpu')  as dt -- coalesce(max()) to return 'cpu' if a cost model does not exist for source
    FROM {{schema | sqlsafe}}.cost_model_map as cmm
    JOIN {{schema | sqlsafe}}.cost_model as cm
        ON cmm.cost_model_id = cm.uuid
    WHERE cmm.provider_uuid = {{source_uuid}}
),
cte_node_usage AS (
    SELECT
        namespace,
        node,
        usage_start,
        sum(pod_effective_usage_cpu_core_hours) as cpu_usage,
        sum(pod_effective_usage_memory_gigabyte_hours) as mem_usage
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY namespace, node, usage_start
),
cte_latest_resources AS (
    SELECT
        pod_labels->>'vm_kubevirt_io_name' AS vm_name,
        CASE WHEN cte_distribution_type.dt = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / sum(cte_node_usage.cpu_usage)
            ELSE sum(pod_effective_usage_memory_gigabyte_hours) / sum(cte_node_usage.mem_usage)
        END as ratio,
        cte_node_usage.node as node_name,
        cte_node_usage.namespace as namespace_name,
        pod_labels as labels,
        cte_node_usage.usage_start
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN cte_distribution_type
        ON cte_distribution_type.source_uuid = ocp.source_uuid
    JOIN cte_node_usage
        ON cte_node_usage.namespace = ocp.namespace
        AND cte_node_usage.node = ocp.node
        AND cte_node_usage.usage_start = ocp.usage_start
    WHERE pod_labels ? 'vm_kubevirt_io_name'
        AND pod_effective_usage_cpu_core_hours != 0
        AND pod_effective_usage_memory_gigabyte_hours != 0
    GROUP BY vm_name, cte_distribution_type.dt, cte_node_usage.usage_start, cte_node_usage.node, cte_node_usage.namespace, pod_labels
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
    id,
    cluster_alias,
    cluster_id,
    namespace,
    node,
    vm_name,
    cost_model_rate_type,
    distributed_cost,
    pod_labels,
    raw_currency,
    resource_ids,
    usage_start,
    usage_end,
    source_uuid
)
SELECT
    uuid_generate_v4() as id,
    cluster_alias,
    cluster_id,
    namespace,
    node,
    latest.vm_name as vm_name,
    cost_model_rate_type,
    sum(distributed_cost * latest.ratio) as distributed_cost, -- the only cost inserted in this statement
    pod_labels,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(latest.usage_start) as usage_start,
    max(latest.usage_start) as usage_end,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN cte_latest_resources as latest
    ON latest.node_name = ocp.node
    AND latest.namespace_name = ocp.namespace
    AND latest.usage_start = ocp.usage_start
WHERE source_uuid = {{source_uuid}}
    AND distributed_cost != 0
GROUP BY cluster_alias, cluster_id, namespace, node, vm_name, pod_labels, cost_model_rate_type
;
