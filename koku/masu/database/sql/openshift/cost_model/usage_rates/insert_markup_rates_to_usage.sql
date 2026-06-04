-- insert_markup_rates_to_usage.sql (Phase 2 Gap Closure — R17 SQL fallback)
--
-- Writes markup costs as RatesToUsage rows with metric_type='markup'.
-- Markup rows flow through RatesToUsage -> OCPCostUIBreakDownP for the
-- breakdown tree only. They are NOT aggregated into cost_model_*_cost
-- columns (the aggregation SQL excludes metric_type='markup').
--
-- The existing ORM UPDATE on daily summary (populate_markup_cost) is
-- preserved unchanged — this SQL reads from it after it runs.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, cluster_id,
--   cost_model_id
-- Note: report_period_id is read from lids.report_period_id, not passed as a bind param.

DELETE FROM {{schema | sqlsafe}}.rates_to_usage
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND metric_type = 'markup';

INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id, rate_id
)
SELECT
    uuid_generate_v4(),
    {{cost_model_id}},
    lids.report_period_id,
    lids.source_uuid,
    lids.usage_start,
    lids.usage_start,
    lids.node,
    lids.namespace,
    lids.cluster_id,
    max(lids.cluster_alias),
    lids.data_source,
    lids.persistentvolumeclaim,
    lids.pod_labels,
    lids.volume_labels,
    lids.all_labels,
    encode(sha256(decode(COALESCE(lids.pod_labels::text, '')
        || '|' || COALESCE(lids.volume_labels::text, '')
        || '|' || COALESCE(lids.all_labels::text, ''), 'escape')), 'hex'),
    'Markup',
    'markup',
    'Infrastructure',
    lids.monthly_cost_type,
    sum(lids.infrastructure_markup_cost),
    lids.cost_category_id,
    NULL::uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
WHERE lids.usage_start >= {{start_date}}
  AND lids.usage_start <= {{end_date}}
  AND lids.source_uuid = {{source_uuid}}
  AND lids.cluster_id = {{cluster_id}}
  AND lids.infrastructure_markup_cost IS NOT NULL
  AND lids.infrastructure_markup_cost != 0
  AND (lids.cost_model_rate_type IS NULL
       OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
GROUP BY
    lids.report_period_id, lids.source_uuid,
    lids.usage_start, lids.node, lids.namespace,
    lids.cluster_id, lids.data_source, lids.persistentvolumeclaim,
    lids.pod_labels, lids.volume_labels, lids.all_labels,
    lids.monthly_cost_type, lids.cost_category_id;
