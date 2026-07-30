DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = {{rate_type}}
    AND lids.monthly_cost_type = {{cost_type}}
    AND lids.pod_labels ? {{tag_key}}
;

CREATE TEMPORARY TABLE label_filtered_daily_summary AS (
    SELECT max(report_period_id) as report_period_id,
    cluster_id,
    max(cluster_alias) as cluster_alias,
    'Pod' as data_source,
    usage_start,
    max(usage_end) as usage_end,
    lids.namespace,
    node,
    max(resource_id) as resource_id,
    {{labels | sqlsafe}},
    sum(pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    sum(pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
    sum(pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    max(pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
    sum(pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    sum(pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    sum(pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(pod_limit_memory_gigabyte_hours) as pod_limit_memory_gigabyte_hours,
    max(node_capacity_cpu_cores) as node_capacity_cpu_cores,
    max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
    max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL::jsonb as volume_labels,
    NULL::decimal as persistentvolumeclaim_capacity_gigabyte,
    NULL::decimal as persistentvolumeclaim_capacity_gigabyte_months,
    NULL::decimal as volume_request_storage_gigabyte_months,
    NULL::decimal as persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    {{rate_type}} as cost_model_rate_type,
    {{cost_model_cpu_cost | sqlsafe}},
    {{cost_model_memory_cost | sqlsafe}},
    {{cost_model_volume_cost | sqlsafe}},
    {{cost_type}} as monthly_cost_type,
    lids.cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
    AND data_source = 'Pod'
    AND pod_labels ? {{tag_key}}
    AND monthly_cost_type IS NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
    AND node_capacity_cpu_core_hours IS NOT NULL
    AND node_capacity_cpu_core_hours != 0
    AND cluster_capacity_cpu_core_hours IS NOT NULL
    AND cluster_capacity_cpu_core_hours != 0
GROUP BY usage_start, source_uuid, cluster_id, node, lids.namespace, lids.pod_labels, lids.cost_category_id
)
;

-- This block is for allocated node usage
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
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
)
SELECT uuid_generate_v4(),
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels::jsonb as pod_labels,
    NULL::decimal as pod_usage_cpu_core_hours,
    NULL::decimal as pod_request_cpu_core_hours,
    NULL::decimal as pod_effective_usage_cpu_core_hours,
    NULL::decimal as pod_limit_cpu_core_hours,
    NULL::decimal as pod_usage_memory_gigabyte_hours,
    NULL::decimal as pod_request_memory_gigabyte_hours,
    NULL::decimal as pod_effective_usage_memory_gigabyte_hours,
    NULL::decimal as pod_limit_memory_gigabyte_hours,
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
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
FROM label_filtered_daily_summary AS lids
;

-- This block is for UNALLOCATED node capacity
-- This is required to get to the full node monthly cost
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
    all_labels,
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
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
)
WITH cte_unallocated AS (
    SELECT uuid_generate_v4() as uuid,
        max(report_period_id) as report_period_id,
        lids.cluster_id,
        max(cluster_alias) as cluster_alias,
        'Pod' as data_source,
        usage_start,
        max(usage_end) as usage_end,
        CASE max(nodes.node_role)
            WHEN 'master' THEN 'Platform unallocated'
            WHEN 'infra' THEN 'Platform unallocated'
            WHEN 'worker' THEN 'Worker unallocated'
        END as namespace,
        lids.node,
        max(lids.resource_id) as resource_id,
        lids.pod_labels::jsonb as pod_labels,
        max(pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
        max(pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
        max(pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
        max(pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
        max(pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
        max(pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
        max(pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
        max(pod_limit_memory_gigabyte_hours) as pod_limit_memory_gigabyte_hours,
        max(lids.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        max(persistentvolumeclaim) as persistentvolumeclaim,
        max(persistentvolume) as persistentvolume,
        max(storageclass) as storageclass,
        NULL::jsonb as volume_labels,
        NULL::decimal as persistentvolumeclaim_capacity_gigabyte,
        NULL::decimal as persistentvolumeclaim_capacity_gigabyte_months,
        NULL::decimal as volume_request_storage_gigabyte_months,
        max(persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
        source_uuid,
        {{rate_type}} as cost_model_rate_type,
        {{unallocated_cost_model_cpu_cost | sqlsafe}},
        {{unallocated_cost_model_memory_cost | sqlsafe}},
        {{unallocated_cost_model_volume_cost | sqlsafe}},
        {{cost_type}} as monthly_cost_type
    FROM label_filtered_daily_summary AS lids
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_nodes as nodes
        ON lids.node = nodes.node
        AND lids.resource_id = nodes.resource_id
    GROUP BY usage_start, source_uuid, lids.cluster_id, lids.node, lids.pod_labels
)
SELECT uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    uc.namespace,
    node,
    resource_id,
    pod_labels,
    pod_labels as all_labels,
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
    cast(cost_model_cpu_cost as decimal),
    cast(cost_model_memory_cost as decimal),
    cast(cost_model_volume_cost as decimal),
    monthly_cost_type,
    cat_ns.cost_category_id as cost_category_id
FROM cte_unallocated AS uc
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
    ON uc.namespace LIKE cat_ns.namespace
;

DROP TABLE label_filtered_daily_summary
;
