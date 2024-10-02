DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = 'worker_distributed'
;

{% if populate %}
WITH cte_narrow_dataset as (
    SELECT * FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
),
worker_cost AS (
    SELECT SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0)+
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0) +
            COALESCE(cost_model_volume_cost, 0)
        ) as worker_cost,
        cnd.usage_start,
        cnd.source_uuid,
        cnd.cluster_id
    FROM cte_narrow_dataset as cnd
    WHERE cnd.namespace = 'Worker unallocated'
    GROUP BY cnd.usage_start, cnd.cluster_id, cnd.source_uuid
),
user_defined_project_sum as (
    SELECT sum(pod_effective_usage_cpu_core_hours) as usage_cpu_sum,
        sum(pod_effective_usage_memory_gigabyte_hours) as usage_memory_sum,
        cluster_id,
        usage_start,
        source_uuid
    FROM cte_narrow_dataset as cnd
    LEFT OUTER JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON cnd.cost_category_id = cat.id
    WHERE cnd.namespace not in ('Worker unallocated', 'Platform unallocated', 'Storage unattributed', 'Network unattributed')
        AND (cost_category_id IS NULL OR cat.name != 'Platform')
    GROUP BY usage_start, cluster_id, source_uuid
),
cte_line_items as (
    SELECT
        max(report_period_id) as report_period_id,
        cnd.cluster_id,
        max(cluster_alias) as cluster_alias,
        cnd.usage_start,
        max(usage_end) as usage_end,
        cnd.namespace,
        cnd.node,
        max(resource_id) as resource_id,
        max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        CASE WHEN {{distribution}} = 'cpu' AND cnd.namespace != 'Worker unallocated' THEN
            CASE WHEN max(udps.usage_cpu_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_cpu_core_hours) / max(udps.usage_cpu_sum)) * max(wc.worker_cost)::decimal
            END
        WHEN {{distribution}} = 'memory' AND cnd.namespace != 'Worker unallocated' THEN
            CASE WHEN max(udps.usage_memory_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_memory_gigabyte_hours) / max(udps.usage_memory_sum)) * max(wc.worker_cost)::decimal
            END
        WHEN cnd.namespace = 'Worker unallocated' THEN
            0 - SUM(
                    COALESCE(infrastructure_raw_cost, 0) +
                    COALESCE(infrastructure_markup_cost, 0) +
                    COALESCE(cost_model_cpu_cost, 0) +
                    COALESCE(cost_model_memory_cost, 0) +
                    COALESCE(cost_model_volume_cost, 0)
                )
        END AS distributed_cost,
        max(cost_category_id) as cost_category_id
    FROM cte_narrow_dataset as cnd
    JOIN worker_cost as wc
        ON wc.usage_start = cnd.usage_start
        AND wc.cluster_id = cnd.cluster_id
    JOIN user_defined_project_sum as udps
        ON udps.usage_start = cnd.usage_start
        AND udps.cluster_id = cnd.cluster_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON cnd.cost_category_id = cat.id
    WHERE cnd.namespace IS NOT NULL
        AND cnd.namespace not in ('Storage unattributed', 'Network unattributed')
        AND data_source = 'Pod'
        AND (cost_category_id IS NULL OR cat.name != 'Platform')
    GROUP BY cnd.usage_start, cnd.node, cnd.namespace, cnd.cluster_id
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
    'worker_distributed' as cost_model_rate_type,
    ctl.distributed_cost,
    ctl.cost_category_id
FROM cte_line_items as ctl
WHERE ctl.distributed_cost != 0;
{% endif %}

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
