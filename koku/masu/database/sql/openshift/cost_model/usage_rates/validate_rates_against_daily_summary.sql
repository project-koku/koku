-- validate_rates_against_daily_summary.sql (CI-only)
--
-- Read-only comparison — does NOT update any rows.
-- Returns rows where RatesToUsage aggregates differ from daily summary.
-- Used in integration tests with known-good cost model configurations.
--
-- If this returns any rows, the aggregation logic has a bug.
--
-- R13: The daily summary does not have label_hash, so we compute it
-- on the fly.  This is acceptable for a CI-only read.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id

SELECT
    lids.uuid,
    lids.usage_start,
    lids.cluster_id,
    lids.namespace,
    lids.node,
    lids.data_source,
    lids.persistentvolumeclaim,
    lids.cost_model_rate_type,
    lids.monthly_cost_type,
    lids.cost_model_cpu_cost      AS expected_cpu,
    lids.cost_model_memory_cost   AS expected_memory,
    lids.cost_model_volume_cost   AS expected_volume,
    agg.total_cpu_cost            AS aggregated_cpu,
    agg.total_memory_cost         AS aggregated_memory,
    agg.total_volume_cost         AS aggregated_volume,
    COALESCE(lids.cost_model_cpu_cost, 0)    - COALESCE(agg.total_cpu_cost, 0)    AS diff_cpu,
    COALESCE(lids.cost_model_memory_cost, 0) - COALESCE(agg.total_memory_cost, 0) AS diff_memory,
    COALESCE(lids.cost_model_volume_cost, 0) - COALESCE(agg.total_volume_cost, 0) AS diff_volume
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
LEFT JOIN (
    SELECT
        usage_start,
        cluster_id,
        namespace,
        node,
        data_source,
        persistentvolumeclaim,
        label_hash,
        cost_model_rate_type,
        monthly_cost_type,
        SUM(CASE WHEN metric_type = 'cpu'     THEN calculated_cost ELSE 0 END) AS total_cpu_cost,
        SUM(CASE WHEN metric_type = 'memory'  THEN calculated_cost ELSE 0 END) AS total_memory_cost,
        SUM(CASE WHEN metric_type = 'storage' THEN calculated_cost ELSE 0 END) AS total_volume_cost
    FROM {{schema | sqlsafe}}.rates_to_usage
    WHERE usage_start >= {{start_date}}
      AND usage_start <= {{end_date}}
      AND source_uuid = {{source_uuid}}
      AND report_period_id = {{report_period_id}}
    GROUP BY usage_start, cluster_id, namespace, node, data_source,
             persistentvolumeclaim, label_hash,
             cost_model_rate_type, monthly_cost_type
) AS agg
  ON  lids.usage_start            = agg.usage_start
  AND lids.cluster_id             = agg.cluster_id
  AND COALESCE(lids.namespace, '')             = COALESCE(agg.namespace, '')
  AND COALESCE(lids.node, '')                  = COALESCE(agg.node, '')
  AND COALESCE(lids.data_source, '')           = COALESCE(agg.data_source, '')
  AND COALESCE(lids.persistentvolumeclaim, '') = COALESCE(agg.persistentvolumeclaim, '')
  AND md5(COALESCE(lids.pod_labels::text, '') || '|' || COALESCE(lids.volume_labels::text, '') || '|' || COALESCE(lids.all_labels::text, ''))
      = agg.label_hash
  AND COALESCE(lids.cost_model_rate_type, '') = COALESCE(agg.cost_model_rate_type, '')
  AND COALESCE(lids.monthly_cost_type, '')    = COALESCE(agg.monthly_cost_type, '')
WHERE lids.usage_start >= {{start_date}}
  AND lids.usage_start <= {{end_date}}
  AND lids.source_uuid = {{source_uuid}}
  AND lids.report_period_id = {{report_period_id}}
  AND lids.cost_model_rate_type IN ('Infrastructure', 'Supplementary')
  AND lids.monthly_cost_type IS NULL
  -- 1e-15 matches calculated_cost decimal_places=15; differences below this are rounding noise.
  AND (
       ABS(COALESCE(lids.cost_model_cpu_cost, 0)    - COALESCE(agg.total_cpu_cost, 0))    > 0.000000000000001
    OR ABS(COALESCE(lids.cost_model_memory_cost, 0) - COALESCE(agg.total_memory_cost, 0)) > 0.000000000000001
    OR ABS(COALESCE(lids.cost_model_volume_cost, 0) - COALESCE(agg.total_volume_cost, 0)) > 0.000000000000001
  );
