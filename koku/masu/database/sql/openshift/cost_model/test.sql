DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = {{rate_type}}
    AND source_uuid = {{source_uuid}}
;

CREATE TEMPORARY TABLE node_to_platform_cost AS (
    SELECT
        SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0)+
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0) +
            COALESCE(cost_model_volume_cost, 0)
        ) as platform_cost,
        lids.node,
        lids.cluster_id,
        lids.namespace
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON lids.namespace LIKE ANY(cat.namespace)
    WHERE lids.cost_category_id IS NOT NULL
        AND lids.cost_category_id IS NOT NULL
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND report_period_id = {{report_period_id}}
    GROUP BY lids.node, lids.node, lids.cluster_id, lids.namespace, cost_category_id
);

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
    distributed_cost
)
WITH potential_platform_line_items AS (
    SELECT max(report_period_id) as report_period_id,
    lids.cluster_id,
    max(cluster_alias) as cluster_alias,
    'Pod' as data_source,
    usage_start,
    max(usage_end) as usage_end,
    lids.namespace,
    lids.node,
    max(resource_id) as resource_id,
    pod_labels,
    max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
    max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
    max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    source_uuid,
    CASE
        WHEN max(npc.platform_cost) != 0
            THEN {{rate_type}}
        WHEN max(npc.platform_cost) = 0
            THEN NULL
    END as cost_model_rate_type,
    CASE
        WHEN {{distribution}} = 'cpu' and max(npc.platform_cost) != 0
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * max(npc.platform_cost)::decimal
        WHEN {{distribution}} = 'memory' and max(npc.platform_cost) != 0
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(npc.platform_cost)::decimal
    END AS distributed_cost
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
INNER JOIN node_to_platform_cost as npc
    on lids.node = npc.node
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
    AND data_source = 'Pod'
    AND lids.namespace != 'Worker unallocated'
    AND node_capacity_cpu_core_hours IS NOT NULL
    AND node_capacity_cpu_core_hours != 0
    AND cluster_capacity_cpu_core_hours IS NOT NULL
    AND cluster_capacity_cpu_core_hours != 0
    AND cost_category_id IS NULL
    AND npc.platform_cost != 0
GROUP BY usage_start, source_uuid, lids.cluster_id, lids.node, lids.namespace, pod_labels
)
SELECT
    uuid_generate_v4(),
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
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    cost_model_rate_type,
    distributed_cost
FROM potential_platform_line_items as ppli
WHERE ppli.cost_model_rate_type = {{rate_type}};

DROP TABLE node_to_platform_cost;
