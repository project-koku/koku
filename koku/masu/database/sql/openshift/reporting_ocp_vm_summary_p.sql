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
cte_latest_resources AS (
    SELECT DISTINCT ON (vm_name)
        all_labels->>'vm_kubevirt_io_name' AS vm_name,
        pod_request_cpu_core_hours AS cpu_request_hours,
        pod_request_memory_gigabyte_hours AS memory_request_hours,
        node as node_name,
        pod_labels as labels
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start::date = (SELECT day FROM second_to_last_day)
        AND pod_request_cpu_core_hours IS NOT NULL
        AND all_labels ? 'vm_kubevirt_io_name'
    ORDER BY vm_name, usage_start DESC
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
    id,
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
    pod_request_cpu_core_hours,
    pod_request_memory_gigabyte_hours,
    infrastructure_markup_cost,
    infrastructure_raw_cost,
    raw_currency,
    resource_ids,
    usage_start,
    usage_end,
    cost_category_id,
    source_uuid
)
SELECT uuid_generate_v4() as id,
    cluster_alias,
    cluster_id,
    namespace,
    max(latest.node_name) as node,
    latest.labels->>'vm_kubevirt_io_name' as vm_name,
    sum(cost_model_cpu_cost) as cost_model_cpu_cost,
    sum(cost_model_memory_cost) as cost_model_memory_cost,
    cost_model_rate_type,
    sum(cost_model_volume_cost) as cost_model_volume_cost,
    sum(distributed_cost) as distributed_cost,
    latest.labels as pod_labels,
    max(latest.cpu_request_hours) as pod_request_cpu_core_hours,
    max(latest.memory_request_hours) as pod_request_memory_gigabyte_hours,
    sum(infrastructure_markup_cost) as infrastructure_markup_cost,
    sum(infrastructure_raw_cost) as infrastructure_raw_cost,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(usage_start) as usage_start,
    max(usage_start) as usage_end,
    max(cost_category_id) as cost_category_id,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
INNER JOIN cte_latest_resources as latest
    ON latest.vm_name = ocp.pod_labels->>'vm_kubevirt_io_name'
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND data_source = 'Pod'
    AND pod_labels ? 'vm_kubevirt_io_name'
    AND namespace IS DISTINCT FROM 'Worker unallocated'
    AND namespace IS DISTINCT FROM 'Platform unallocated'
    AND namespace IS DISTINCT FROM 'Network unattributed'
    AND namespace IS DISTINCT FROM 'Storage unattributed'
    AND (
        COALESCE(cost_model_cpu_cost, 0)
        + COALESCE(cost_model_memory_cost, 0)
        + COALESCE(cost_model_volume_cost, 0)
        + COALESCE(distributed_cost, 0)
        + COALESCE(infrastructure_raw_cost, 0)
        + COALESCE(infrastructure_markup_cost, 0)) != 0
GROUP BY cluster_alias, cluster_id, namespace, latest.node_name, vm_name, cost_model_rate_type, latest.labels
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
cte_latest_resources AS (
    SELECT DISTINCT ON (vm_name)
        all_labels->>'vm_kubevirt_io_name' AS vm_name,
        pod_request_cpu_core_hours AS cpu_request_hours,
        pod_request_memory_gigabyte_hours AS memory_request_hours,
        CASE WHEN cte_distribution_type.dt = 'cpu'
            THEN pod_effective_usage_cpu_core_hours / node_capacity_cpu_core_hours
            ELSE pod_effective_usage_memory_gigabyte_hours / node_capacity_memory_gigabyte_hours
        END as ratio,
        node as node_name,
        namespace as namespace_name,
        pod_labels as labels
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN cte_distribution_type
        ON cte_distribution_type.source_uuid = ocp.source_uuid
    WHERE usage_start::date = (SELECT day FROM second_to_last_day)
        AND pod_request_cpu_core_hours IS NOT NULL
        AND all_labels ? 'vm_kubevirt_io_name'
    ORDER BY vm_name, usage_start DESC
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
    latest.node_name as node,
    latest.labels->>'vm_kubevirt_io_name' as vm_name,
    'distributed_rates' as cost_model_rate_type,
    sum(distributed_cost) * latest.ratio as distributed_cost, -- the only cost inserted in this statement
    latest.labels as pod_labels,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(usage_start) as usage_start,
    max(usage_start) as usage_end,
    {{source_uuid}}::uuid as source_uuid
FROM org1234567_mskarbek.reporting_ocpusagelineitem_daily_summary as ocp
JOIN cte_latest_resources as latest
    ON latest.node_name = ocp.node AND latest.namespace_name = ocp.namespace
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
GROUP BY cluster_alias, cluster_id, namespace, latest.node_name, latest.ratio, vm_name, latest.labels
;
