CREATE TEMPORARY TABLE node_to_platform_cost AS (
SELECT
    SUM(
        COALESCE(infrastructure_raw_cost, 0) +
        COALESCE(infrastructure_markup_cost, 0)+
        COALESCE(cost_model_cpu_cost, 0) +
        COALESCE(cost_model_memory_cost, 0) +
        COALESCE(cost_model_volume_cost, 0)
    ) as platform_cost,
    lids.node
FROM org1234567.reporting_ocpusagelineitem_daily_summary as lids
LEFT JOIN org1234567.reporting_ocp_cost_category AS cat
    ON lids.namespace LIKE ANY(cat.namespace)
WHERE lids.cost_category_id IS NOT NULL
    AND usage_start >= '2023-03-01'::date
    AND usage_start <= '2023-03-06'::date
    AND report_period_id = 11
    AND cost_model_rate_type != 'platform_distributed'
    AND source_uuid = 'c8675449-8a88-493d-afea-e6cbfccc4a79'
GROUP BY lids.node, source_uuid, cost_category_id
);

--     platform_cost    |   node    |    cluster_id    |        namespace
-- ---------------------+-----------+------------------+--------------------------
--  389.142590154838710 | master_1  | my-ocp-cluster-3 | Platform unallocated
--  129.760635651612905 | master_1  | my-ocp-cluster-3 | openshift-kube-apiserver
--  129.777158961612905 | master_3  | my-ocp-cluster-3 | kube-system
--  430.074529193225805 | compute_3 | my-ocp-cluster-3 | Platform unallocated

SELECT
    SUM(distributed_cost),
    node,
    cluster_id,
    namespace,
    cost_category_id
FROM org1234567.reporting_ocpusagelineitem_daily_summary as lids
WHERE usage_start >= '2023-03-01'::date
    AND usage_start <= '2023-03-06'::date
    AND report_period_id = 11
    AND cost_model_rate_type = 'platform_distributed'
    AND source_uuid = 'c8675449-8a88-493d-afea-e6cbfccc4a79'
GROUP BY lids.node, lids.node, lids.cluster_id, lids.namespace, cost_category_id;


SELECT max(report_period_id) as report_period_id,
    cluster_id,
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
    'platform-distributed' as cost_model_rate_type,
    CASE
        WHEN 'cpu' = 'cpu' and max(npc.node) = lids.node
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * max(npc.platform_cost)::decimal
        WHEN 'cpu' = 'memory' and max(npc.node) = lids.node
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(npc.platform_cost)::decimal
    END AS distribution_cost,
    0 as cost_model_volume_cost,
    cost_category_id,
    max(npc.platform_cost) as platform_cost,
    sum(pod_effective_usage_cpu_core_hours) as hourz,
    max(node_capacity_cpu_core_hours) as cap,
    sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) as ratio
FROM reporting_ocpusagelineitem_daily_summary AS lids
INNER JOIN node_to_platform_cost as npc
    on lids.node = npc.node
WHERE usage_start >= '2023-03-01'::date
    AND usage_start <= '2023-03-06'::date
    AND report_period_id = 11
    AND lids.namespace IS NOT NULL
    AND data_source = 'Pod'
    AND lids.namespace != 'Worker unallocated'
    AND node_capacity_cpu_core_hours IS NOT NULL
    AND node_capacity_cpu_core_hours != 0
    AND cluster_capacity_cpu_core_hours IS NOT NULL
    AND cluster_capacity_cpu_core_hours != 0
    AND cost_category_id IS NULL
    AND npc.platform_cost != 0
GROUP BY usage_start, source_uuid, cluster_id, lids.node,  namespace, pod_labels, cost_category_id
;
