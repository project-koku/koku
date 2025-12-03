WITH cte_narrow_dataset as (
    SELECT
        lids.usage_start,
        lids.source_uuid,
        lids.cost_category_id,
        lids.pod_effective_usage_cpu_core_hours,
        lids.pod_effective_usage_memory_gigabyte_hours,
        lids.infrastructure_raw_cost,
        lids.infrastructure_markup_cost,
        lids.cost_model_cpu_cost,
        lids.cost_model_memory_cost,
        lids.cost_model_volume_cost,
        lids.report_period_id,
        lids.cluster_id,
        lids.cluster_alias,
        lids.data_source,
        lids.usage_end,
        lids.namespace,
        lids.node,
        lids.resource_id,
        lids.node_capacity_cpu_cores,
        lids.node_capacity_cpu_core_hours,
        lids.node_capacity_memory_gigabytes,
        lids.node_capacity_memory_gigabyte_hours,
        lids.cluster_capacity_cpu_core_hours,
        lids.cluster_capacity_memory_gigabyte_hours
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace != 'Storage unattributed'
        AND lids.namespace != 'Network unattributed'
        AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
),
worker_cost AS (
    SELECT SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0)+
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0) +
            COALESCE(cost_model_volume_cost, 0)
        ) as worker_cost,
        filtered.usage_start,
        filtered.source_uuid,
        filtered.cluster_id
    FROM cte_narrow_dataset as filtered
    WHERE filtered.namespace = 'Worker unallocated'
    GROUP BY filtered.usage_start, filtered.cluster_id, filtered.source_uuid
),
user_defined_project_sum as (
    SELECT sum(pod_effective_usage_cpu_core_hours) as usage_cpu_sum,
        sum(pod_effective_usage_memory_gigabyte_hours) as usage_memory_sum,
        cluster_id,
        usage_start,
        source_uuid
    FROM cte_narrow_dataset as filtered
    WHERE filtered.namespace != 'Worker unallocated'
    GROUP BY usage_start, cluster_id, source_uuid
),
cte_line_items as (
    SELECT
        max(report_period_id) as report_period_id,
        filtered.cluster_id,
        max(cluster_alias) as cluster_alias,
        filtered.usage_start,
        max(usage_end) as usage_end,
        filtered.namespace,
        filtered.node,
        max(resource_id) as resource_id,
        max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        CASE WHEN {{distribution}} = 'cpu' AND filtered.namespace != 'Worker unallocated' THEN
            CASE WHEN max(udps.usage_cpu_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_cpu_core_hours) / max(udps.usage_cpu_sum)) * max(wc.worker_cost)::decimal
            END
        WHEN {{distribution}} = 'memory' AND filtered.namespace != 'Worker unallocated' THEN
            CASE WHEN max(udps.usage_memory_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_memory_gigabyte_hours) / max(udps.usage_memory_sum)) * max(wc.worker_cost)::decimal
            END
        WHEN filtered.namespace = 'Worker unallocated' THEN
            0 - SUM(
                    COALESCE(infrastructure_raw_cost, 0) +
                    COALESCE(infrastructure_markup_cost, 0) +
                    COALESCE(cost_model_cpu_cost, 0) +
                    COALESCE(cost_model_memory_cost, 0) +
                    COALESCE(cost_model_volume_cost, 0)
                )
        END AS distributed_cost,
        max(cost_category_id) as cost_category_id
    FROM cte_narrow_dataset as filtered
    JOIN worker_cost as wc
        ON wc.usage_start = filtered.usage_start
        AND wc.cluster_id = filtered.cluster_id
    JOIN user_defined_project_sum as udps
        ON udps.usage_start = filtered.usage_start
        AND udps.cluster_id = filtered.cluster_id
    WHERE filtered.namespace IS NOT NULL
        AND data_source = 'Pod'
    GROUP BY filtered.usage_start, filtered.node, filtered.namespace, filtered.cluster_id
)
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
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    source_uuid,
    cost_model_rate_type,
    distributed_cost,
    cost_category_id
)
SELECT
    uuid_generate_v4(),
    ctl.report_period_id,
    ctl.cluster_id,
    ctl.cluster_alias,
    'Pod' as data_source,
    ctl.usage_start,
    ctl.usage_end,
    ctl.namespace,
    ctl.node,
    ctl.resource_id,
    ctl.node_capacity_cpu_cores,
    ctl.node_capacity_cpu_core_hours,
    ctl.node_capacity_memory_gigabytes,
    ctl.node_capacity_memory_gigabyte_hours,
    ctl.cluster_capacity_cpu_core_hours,
    ctl.cluster_capacity_memory_gigabyte_hours,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    {{cost_model_rate_type}} as cost_model_rate_type,
    ctl.distributed_cost,
    ctl.cost_category_id
FROM cte_line_items as ctl
WHERE ctl.distributed_cost != 0;

-- Notes:
-- The sql below calculates the worker unallocated cost at the cluster
-- level. Then sums the user/worker projects relative uage to use as a
-- new denominator in our distribution equation.

-- Validation SQL
-- SELECT
--     sum(distributed_cost) as distributed_cost,
--     lids.node,
--     lids.usage_start,
--     lids.namespace,
--     lids.cluster_id
-- FROM org1234567.reporting_ocpusagelineitem_daily_summary AS lids
-- WHERE distributed_cost IS NOT NULL
-- AND usage_start = '2023-03-01'
-- AND lids.namespace != 'Worker unallocated'
-- AND lids.namespace != 'Network unattributed'
-- AND cost_model_rate_type = 'worker_distributed'
-- GROUP BY lids.usage_start, lids.cluster_id, lids.node, lids.namespace;

-- Note
-- To show the negated distributed cost just change lids.namespace = 'Worker unallocated'
