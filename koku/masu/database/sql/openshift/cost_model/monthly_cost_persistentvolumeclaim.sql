-- monthly_cost_persistentvolumeclaim.sql (Phase 3: RTU INSERT)
--
-- Inserts monthly PVC costs into rates_to_usage.
-- Cost is distributed evenly across PVCs in a namespace.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   rate, cost_type, rate_type, distribution, cost_model_id,
--   rate_uuid, custom_name

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
        AND lids.infrastructure_monthly_cost_json IS NULL
    GROUP BY lids.usage_start, lids.cluster_id, lids.namespace
)
SELECT uuid_generate_v4(),
    {{cost_model_id}},
    max(report_period_id),
    lids.source_uuid,
    lids.usage_start,
    max(lids.usage_end),
    lids.node,
    lids.namespace,
    lids.cluster_id,
    max(lids.cluster_alias),
    'Storage',
    lids.persistentvolumeclaim,
    NULL::jsonb,
    lids.volume_labels,
    lids.volume_labels::jsonb,
    encode(sha256(decode('|' || COALESCE(lids.volume_labels::text, '') || '|' || COALESCE(lids.volume_labels::text, ''), 'escape')), 'hex'),
    {{custom_name}},
    {{metric_type}},
    {{rate_type}},
    {{cost_type}},
    CASE
        WHEN {{cost_type}} = 'PVC'
            THEN {{rate}}::decimal / vc.pvc_count
        ELSE 0
    END,
    lids.cost_category_id,
    {{rate_uuid}}
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
    AND monthly_cost_type IS NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
    AND persistentvolumeclaim_capacity_gigabyte_months IS NOT NULL
    AND persistentvolumeclaim_capacity_gigabyte_months != 0
GROUP BY lids.usage_start, lids.source_uuid, lids.cluster_id, lids.node, lids.namespace, lids.persistentvolumeclaim, lids.persistentvolume, lids.volume_labels, vc.pvc_count, lids.cost_category_id
;
