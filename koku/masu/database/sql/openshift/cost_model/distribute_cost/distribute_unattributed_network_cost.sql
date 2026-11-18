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
        lids.cluster_capacity_memory_gigabyte_hours,
        lids.raw_currency
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace != 'Storage unattributed'
        AND lids.namespace != 'Worker unallocated'
        AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
),
unattributed_network_cost AS (
    SELECT SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0)+
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0) +
            COALESCE(cost_model_volume_cost, 0)
        ) as unattributed_cost,
        filtered.usage_start
    FROM cte_narrow_dataset as filtered
    WHERE filtered.namespace = 'Network unattributed'
    GROUP BY filtered.usage_start
),
user_defined_project_sum as (
    SELECT sum(pod_effective_usage_cpu_core_hours) as usage_cpu_sum,
        sum(pod_effective_usage_memory_gigabyte_hours) as usage_memory_sum,
        cluster_id,
        usage_start,
        source_uuid
    FROM cte_narrow_dataset as filtered
    WHERE filtered.namespace != 'Network unattributed'
    GROUP BY usage_start, cluster_id, source_uuid
),
cte_line_items as (
    SELECT
        max(report_period_id) as report_period_id,
        filtered.cluster_id,
        max(cluster_alias) as cluster_alias,
        filtered.data_source as data_source,
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
        CASE WHEN {{distribution}} = 'cpu' AND namespace != 'Network unattributed' THEN
            CASE WHEN max(udps.usage_cpu_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_cpu_core_hours) / max(udps.usage_cpu_sum)) * max(usc.unattributed_cost)::decimal
            END
        WHEN {{distribution}} = 'memory' AND namespace != 'Network unattributed'  THEN
            CASE WHEN max(udps.usage_memory_sum) <= 0 THEN
                0
            ELSE
                (sum(pod_effective_usage_memory_gigabyte_hours) / max(udps.usage_memory_sum)) * max(usc.unattributed_cost)::decimal
            END
        WHEN namespace = 'Network unattributed' THEN
            0 - SUM(
                    COALESCE(infrastructure_raw_cost, 0) +
                    COALESCE(infrastructure_markup_cost, 0) +
                    COALESCE(cost_model_cpu_cost, 0) +
                    COALESCE(cost_model_memory_cost, 0) +
                    COALESCE(cost_model_volume_cost, 0)
                )
        END AS distributed_cost,
        max(cost_category_id) as cost_category_id,
        max(raw_currency) as raw_currency
    FROM cte_narrow_dataset as filtered
    LEFT JOIN unattributed_network_cost as usc
        ON usc.usage_start = filtered.usage_start
    LEFT JOIN user_defined_project_sum as udps
        ON udps.usage_start = filtered.usage_start
        AND udps.cluster_id = filtered.cluster_id
    WHERE filtered.namespace IS NOT NULL
    GROUP BY filtered.usage_start, filtered.node, filtered.namespace, filtered.cluster_id, cost_category_id, filtered.data_source
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
    cost_category_id,
    raw_currency
)
SELECT
    uuid_generate_v4(),
    ctl.report_period_id,
    ctl.cluster_id,
    ctl.cluster_alias,
    ctl.data_source as data_source,
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
    ctl.cost_category_id,
    ctl.raw_currency
FROM cte_line_items as ctl
WHERE ctl.distributed_cost != 0;
