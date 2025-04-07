INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
        coalesce(max(cm.distribution), 'cpu')  as dt -- coalesce(max()) to return 'cpu' if a cost model does not exist for source
    FROM postgres.{{schema | sqlsafe}}.cost_model_map as cmm
    JOIN postgres.{{schema | sqlsafe}}.cost_model as cm
        ON cmm.cost_model_id = cm.uuid
    WHERE cmm.provider_uuid = cast({{source_uuid}} as uuid)
),
cte_node_usage as (
    -- get the total cpu/mem usage of a node
    SELECT
        usage_start,
        node,
        sum(pod_effective_usage_cpu_core_hours) as cpu_usage,
        sum(pod_effective_usage_memory_gigabyte_hours) as mem_usage
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= date({{start_date}})
        AND usage_start <= date({{end_date}})
        AND source_uuid = cast({{source_uuid}} as uuid)
    GROUP BY usage_start, node
),
cte_cluster as (
    -- get the total number of hours a cluster ran in a day and the total number of nodes
    SELECT
        date(interval_start) as interval_day,
        cast(count(distinct interval_start) as decimal(24, 9)) as cluster_hours,
        cast(count(distinct node) as decimal(24, 9)) as node_count
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE source = {{source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
    GROUP BY date(interval_start)
)

SELECT uuid(),
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
    -- distribute the cost evenly amongst the namespaces across nodes
    -- cost = (# hours running / number of nodes) * rate * (namespace usage on node / total usage of that node)
    CASE WHEN cte_distribution_type.dt = 'cpu'
        THEN ( max(cte_cluster.cluster_hours)/max(cte_cluster.node_count) * cast({{cluster_cost_per_hour}} as decimal(24, 9)) * sum(lids.pod_effective_usage_cpu_core_hours)/sum(cte_node_usage.cpu_usage) )
        ELSE 0
    END as cost_model_cpu_cost,
    CASE WHEN cte_distribution_type.dt = 'memory'
        THEN ( max(cte_cluster.cluster_hours)/max(cte_cluster.node_count) * cast({{cluster_cost_per_hour}} as decimal(24, 9)) * sum(lids.pod_effective_usage_memory_gigabyte_hours)/sum(cte_node_usage.mem_usage) )
        ELSE 0
    END as cost_model_memory_cost,
    0 as cost_model_volume_cost,
    lids.cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
JOIN cte_distribution_type
    ON cte_distribution_type.source_uuid = lids.source_uuid
JOIN cte_node_usage
    ON lids.source_uuid = cast({{source_uuid}} as uuid)
    AND lids.usage_start = cte_node_usage.usage_start
    AND lids.node = cte_node_usage.node
JOIN cte_cluster
    ON lids.source_uuid = cast({{source_uuid}} as uuid)
    AND lids.usage_start = cte_cluster.interval_day
WHERE lids.usage_start >= date({{start_date}})
    AND lids.usage_start <= date({{end_date}})
    AND lids.source_uuid = cast({{source_uuid}} as uuid)
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.monthly_cost_type IS NULL
    AND lids.pod_effective_usage_cpu_core_hours > 0
GROUP BY lids.usage_start,
         lids.cluster_id,
         lids.namespace,
         lids.node,
         lids.resource_id,
         lids.data_source,
         lids.cost_category_id,
         lids.pod_labels
;
