-- monthly_cost_persistentvolumeclaim_by_tag.sql (Phase 3: RTU INSERT)
--
-- Inserts per-rate monthly tag-based PVC costs into rates_to_usage.
-- Cost is distributed evenly across PVCs matching a tag key.
-- CASE statements for per-tag-value cost calculation are built in Python.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   rate_type, cost_type, tag_key, labels,
--   cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
--   cost_model_id, rate_uuid, custom_name

DELETE FROM {{schema | sqlsafe}}.rates_to_usage AS rtu
WHERE rtu.usage_start >= {{start_date}}::date
    AND rtu.usage_start <= {{end_date}}::date
    AND rtu.report_period_id = {{report_period_id}}
    AND rtu.cost_model_rate_type = {{rate_type}}
    AND rtu.monthly_cost_type = 'PVC'
;


INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id, rate_id
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
        lids.persistentvolumeclaim,
        lids.persistentvolume,
        max(lids.storageclass) as storageclass,
        {{labels | sqlsafe}},
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
        AND (
            lids.cost_model_rate_type IS NULL
            OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
        )
        AND persistentvolumeclaim_capacity_gigabyte_months IS NOT NULL
        AND persistentvolumeclaim_capacity_gigabyte_months != 0
    GROUP BY lids.usage_start, lids.source_uuid, lids.cluster_id, lids.node, lids.namespace, lids.persistentvolumeclaim, lids.persistentvolume, lids.volume_labels, vc.pvc_count, lids.cost_category_id
)
SELECT uuid,
    {{cost_model_id}},
    report_period_id,
    source_uuid,
    usage_start,
    usage_end,
    node,
    namespace,
    cluster_id,
    cluster_alias,
    data_source,
    persistentvolumeclaim,
    pod_labels,
    volume_labels::jsonb,
    volume_labels::jsonb,
    md5('|' || COALESCE(volume_labels::text, '') || '|' || COALESCE(volume_labels::text, '')),
    {{custom_name}},
    'storage',
    cost_model_rate_type,
    monthly_cost_type,
    cost_model_volume_cost,
    cost_category_id,
    {{rate_uuid}}
FROM cte_filtered_data
;
