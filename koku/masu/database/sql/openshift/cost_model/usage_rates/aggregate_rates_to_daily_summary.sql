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
-- The base CTE reads columns that rates_to_usage does not store
-- (resource_id, persistentvolume, storageclass, capacity columns) from
-- the original daily summary base rows, using the same GROUP BY keys
-- and WHERE filter as insert_usage_rates_to_usage.sql's base CTE.
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

-- Step 2: INSERT aggregated rows from RatesToUsage, JOINed with base rows
-- for columns not stored in rates_to_usage.
WITH base AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        lids.namespace,
        lids.data_source,
        lids.persistentvolumeclaim,
        md5(COALESCE(lids.pod_labels::text, '')
            || '|' || COALESCE(lids.volume_labels::text, '')
            || '|' || COALESCE(lids.all_labels::text, '')) AS label_hash,
        lids.cost_category_id,
        max(lids.resource_id) AS resource_id,
        max(lids.persistentvolume) AS persistentvolume,
        max(lids.storageclass) AS storageclass,
        max(lids.node_capacity_cpu_cores) AS node_capacity_cpu_cores,
        max(lids.node_capacity_cpu_core_hours) AS node_capacity_cpu_core_hours,
        max(lids.node_capacity_memory_gigabytes) AS node_capacity_memory_gigabytes,
        max(lids.node_capacity_memory_gigabyte_hours) AS node_capacity_memory_gigabyte_hours,
        max(lids.cluster_capacity_cpu_core_hours) AS cluster_capacity_cpu_core_hours,
        max(lids.cluster_capacity_memory_gigabyte_hours) AS cluster_capacity_memory_gigabyte_hours
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}
      AND lids.usage_start <= {{end_date}}
      AND lids.source_uuid = {{source_uuid}}
      AND lids.report_period_id = {{report_period_id}}
      AND lids.namespace IS NOT NULL
      AND lids.cost_model_rate_type IS NULL
    GROUP BY
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        lids.namespace,
        lids.data_source,
        lids.persistentvolumeclaim,
        lids.pod_labels,
        lids.volume_labels,
        lids.all_labels,
        lids.cost_category_id
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid, report_period_id, cluster_id, cluster_alias, namespace, node,
    resource_id,
    usage_start, usage_end, data_source, source_uuid,
    persistentvolumeclaim, persistentvolume, storageclass,
    pod_labels, volume_labels, all_labels,
    node_capacity_cpu_cores, node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes, node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours, cluster_capacity_memory_gigabyte_hours,
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
    MAX(base.resource_id),
    rtu.usage_start,
    rtu.usage_start + interval '1 day' AS usage_end,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    MAX(base.persistentvolume),
    MAX(base.storageclass),
    MIN(rtu.pod_labels::text)::jsonb AS pod_labels,
    MIN(rtu.volume_labels::text)::jsonb AS volume_labels,
    MIN(rtu.all_labels::text)::jsonb AS all_labels,
    MAX(base.node_capacity_cpu_cores),
    MAX(base.node_capacity_cpu_core_hours),
    MAX(base.node_capacity_memory_gigabytes),
    MAX(base.node_capacity_memory_gigabyte_hours),
    MAX(base.cluster_capacity_cpu_core_hours),
    MAX(base.cluster_capacity_memory_gigabyte_hours),
    rtu.cost_category_id,
    rtu.cost_model_rate_type,
    SUM(CASE WHEN rtu.metric_type = 'cpu'     THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'memory'  THEN rtu.calculated_cost ELSE 0 END),
    SUM(CASE WHEN rtu.metric_type = 'storage' THEN rtu.calculated_cost ELSE 0 END),
    SUM(COALESCE(rtu.distributed_cost, 0))
FROM {{schema | sqlsafe}}.rates_to_usage rtu
LEFT JOIN base
    ON  rtu.usage_start              = base.usage_start
    AND rtu.cluster_id               = base.cluster_id
    AND rtu.node         IS NOT DISTINCT FROM base.node
    AND rtu.namespace                = base.namespace
    AND rtu.data_source  IS NOT DISTINCT FROM base.data_source
    AND rtu.persistentvolumeclaim IS NOT DISTINCT FROM base.persistentvolumeclaim
    AND rtu.label_hash               = base.label_hash
    AND rtu.cost_category_id IS NOT DISTINCT FROM base.cost_category_id
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
