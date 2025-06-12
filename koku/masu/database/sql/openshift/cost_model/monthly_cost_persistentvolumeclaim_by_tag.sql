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
    all_labels,
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
WITH cte_volume_count AS (
    SELECT usage_start,
        cluster_id,
        namespace,
        count(DISTINCT persistentvolumeclaim) as pvc_count
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    WHERE lids.persistentvolumeclaim IS NOT NULL
        AND lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.volume_labels ? {{tag_key}}
        AND lids.infrastructure_monthly_cost_json IS NULL
    GROUP BY lids.usage_start, lids.cluster_id, lids.namespace
),
cte_filtered_data AS (
    SELECT uuid_generate_v4() as uuid,
        max(report_period_id) as report_period_id,
        lids.cluster_id,
        max(lids.cluster_alias) as cluster_alias,
        'Storage' as data_source,
        lids.usage_start,
        max(lids.usage_end) as usage_end,
        lids.namespace,
        lids.node,
        max(lids.resource_id) as resource_id,
        NULL::jsonb as pod_labels,
        NULL::decimal as pod_usage_cpu_core_hours,
        NULL::decimal as pod_request_cpu_core_hours,
        NULL::decimal as pod_effective_usage_cpu_core_hours,
        NULL::decimal as pod_limit_cpu_core_hours,
        NULL::decimal as pod_usage_memory_gigabyte_hours,
        NULL::decimal as pod_request_memory_gigabyte_hours,
        NULL::decimal as pod_effective_usage_memory_gigabyte_hours,
        NULL::decimal as pod_limit_memory_gigabyte_hours,
        max(lids.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(lids.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(lids.node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(lids.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(lids.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(lids.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        lids.persistentvolumeclaim,
        lids.persistentvolume,
        max(lids.storageclass) as storageclass,
        {{labels | sqlsafe}},
        NULL::decimal as persistentvolumeclaim_capacity_gigabyte,
        NULL::decimal as persistentvolumeclaim_capacity_gigabyte_months,
        NULL::decimal as volume_request_storage_gigabyte_months,
        NULL::decimal as persistentvolumeclaim_usage_gigabyte_months,
        lids.source_uuid,
        {{rate_type}} as cost_model_rate_type,
        {{cost_model_cpu_cost | sqlsafe}},
        {{cost_model_memory_cost | sqlsafe}},
        {{cost_model_volume_cost | sqlsafe}},
        {{cost_type}} as monthly_cost_type,
        lids.cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    JOIN cte_volume_count AS vc
        ON lids.usage_start = vc.usage_start
            AND lids.cluster_id = vc.cluster_id
            AND lids.namespace = vc.namespace
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.persistentvolumeclaim IS NOT NULL
        AND lids.data_source = 'Storage'
        AND lids.volume_labels ? {{tag_key}}
        AND lids.infrastructure_monthly_cost_json IS NULL
        AND monthly_cost_type IS NULL
        AND persistentvolumeclaim_capacity_gigabyte_months IS NOT NULL
        AND persistentvolumeclaim_capacity_gigabyte_months != 0
    GROUP BY lids.usage_start, lids.source_uuid, lids.cluster_id, lids.node, lids.namespace, lids.persistentvolumeclaim, lids.persistentvolume, lids.volume_labels, vc.pvc_count, lids.cost_category_id
)
SELECT uuid,
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
    volume_labels::jsonb,
    volume_labels::jsonb as all_labels,
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
FROM cte_filtered_data
;
