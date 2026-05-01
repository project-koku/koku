-- aggregate_rates_to_daily_summary.sql (Phase 2+)
--
-- Rolls up per-rate RatesToUsage rows into daily summary cost columns.
-- Runs AFTER all per-rate INSERTs and BEFORE cost distribution (step 5).
-- Replaces usage_costs.sql direct-write starting in Phase 2.
--
-- Pattern matches usage_costs.sql: DELETE existing cost model rows, then
-- INSERT aggregated rows with uuid_generate_v4() and cost_model_rate_type.
--
-- The WHERE metric_type IN ('cpu', 'memory', 'storage') excludes markup
-- and gpu rows from the three cost_model columns.  GPU costs are written
-- by the tag-based cost SQL.  Markup is handled by the existing ORM path.
--
-- R13: GROUP BY uses label_hash (32-char md5) instead of 3 JSONB columns.
-- JSONB columns are retrieved via MIN() over the text representation,
-- which is functionally correct because all rows sharing a label_hash
-- have identical JSONB values, and avoids materializing a full array.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id

-- Step 1: Delete existing cost model rows (same scope as usage_costs.sql DELETE)
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}}
  AND cost_model_rate_type IS NOT NULL
  AND cost_model_rate_type IN ('Infrastructure', 'Supplementary')
  AND monthly_cost_type IS NULL;

-- Step 2: INSERT aggregated rows from RatesToUsage
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid, report_period_id, cluster_id, cluster_alias, namespace, node,
    usage_start, usage_end, data_source, source_uuid,
    persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    cost_category_id, cost_model_rate_type,
    cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
    distributed_cost
)
SELECT
    uuid_generate_v4(),
    rtu.report_period_id,
    rtu.cluster_id,
    rtu.cluster_alias,
    rtu.namespace,
    rtu.node,
    rtu.usage_start,
    rtu.usage_start + interval '1 day' AS usage_end,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    MIN(rtu.pod_labels::text)::jsonb AS pod_labels,
    MIN(rtu.volume_labels::text)::jsonb AS volume_labels,
    MIN(rtu.all_labels::text)::jsonb AS all_labels,
    rtu.cost_category_id,
    rtu.cost_model_rate_type,
    SUM(CASE WHEN rtu.metric_type = 'cpu'     THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'memory'  THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'storage' THEN rtu.calculated_cost ELSE 0 END),
    SUM(COALESCE(rtu.distributed_cost, 0))
FROM {{schema | sqlsafe}}.rates_to_usage rtu
WHERE rtu.usage_start >= {{start_date}}
  AND rtu.usage_start <= {{end_date}}
  AND rtu.source_uuid = {{source_uuid}}
  AND rtu.report_period_id = {{report_period_id}}
  AND rtu.metric_type IN ('cpu', 'memory', 'storage')
  AND rtu.monthly_cost_type IS NULL
GROUP BY
    rtu.report_period_id,
    rtu.cluster_id,
    rtu.cluster_alias,
    rtu.namespace,
    rtu.node,
    rtu.usage_start,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    rtu.label_hash,
    rtu.cost_category_id,
    rtu.cost_model_rate_type;
