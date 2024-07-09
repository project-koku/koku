DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = 'unattributed_network'
;

{% if populate %}
WITH unattributed_network_cost AS (
    SELECT SUM(
            COALESCE(infrastructure_raw_cost, 0) +
            COALESCE(infrastructure_markup_cost, 0)+
            COALESCE(cost_model_cpu_cost, 0) +
            COALESCE(cost_model_memory_cost, 0) +
            COALESCE(cost_model_volume_cost, 0)
        ) as unattributed_cost,
        lids.usage_start
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace = 'Network unattributed'
    GROUP BY lids.usage_start
),
user_defined_project_sum as (
    SELECT sum(pod_effective_usage_cpu_core_hours) as usage_cpu_sum,
        sum(pod_effective_usage_memory_gigabyte_hours) as usage_memory_sum,
        cluster_id,
        usage_start,
        source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND report_period_id = {{report_period_id}}
        AND lids.namespace not in ('Worker unallocated', 'Platform unallocated', 'Storage unattributed', 'Network unattributed')
        AND (cost_category_id IS NULL OR cat.name != 'Platform')
    GROUP BY usage_start, cluster_id, source_uuid
),
cte_line_items as (
    SELECT
        max(report_period_id) as report_period_id,
        lids.cluster_id,
        max(cluster_alias) as cluster_alias,
        lids.data_source as data_source,
        lids.usage_start,
        max(usage_end) as usage_end,
        lids.namespace,
        lids.node,
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
        max(cost_category_id) as cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    LEFT JOIN unattributed_network_cost as usc
        ON usc.usage_start = lids.usage_start
    LEFT JOIN user_defined_project_sum as udps
        ON udps.usage_start = lids.usage_start
        AND udps.cluster_id = lids.cluster_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category AS cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND report_period_id = {{report_period_id}}
        AND lids.namespace IS NOT NULL
        AND lids.namespace not in ('Worker unallocated', 'Platform unallocated', 'Storage unattributed')
        AND (cost_category_id IS NULL OR cat.name != 'Platform')
    GROUP BY lids.usage_start, lids.node, lids.namespace, lids.cluster_id, cost_category_id, lids.data_source
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
    distributed_cost,
    cost_category_id
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
    NULL as pod_labels,
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    ctl.node_capacity_cpu_cores,
    ctl.node_capacity_cpu_core_hours,
    ctl.node_capacity_memory_gigabytes,
    ctl.node_capacity_memory_gigabyte_hours,
    ctl.cluster_capacity_cpu_core_hours,
    ctl.cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    'unattributed_network' as cost_model_rate_type,
    ctl.distributed_cost,
    ctl.cost_category_id
FROM cte_line_items as ctl
WHERE ctl.distributed_cost != 0;
{% endif %}
