-- aggregate_rates_to_daily_summary.sql (Phase 3/4)
--
-- Rolls up per-rate RatesToUsage rows into daily summary cost columns.
-- Runs AFTER all per-rate INSERTs (usage, monthly, tag) and AFTER
-- cost distribution (Phase 4 re-ordered: distribute -> aggregate -> markup).
--
-- Block 1: Aggregates usage-cost RTU rows (monthly_cost_type IS NULL).
--   Capacity columns are read directly from RatesToUsage (denormalized at
--   insert time by insert_usage_rates_to_usage.sql) instead of re-JOINing to
--   the daily summary. That JOIN required 4 nullable-column IS NOT DISTINCT
--   FROM predicates (node, data_source, persistentvolumeclaim, cost_category_id)
--   which Postgres cannot use a B-tree index for, making it the single most
--   expensive step in the cost-model pipeline (see risk-register.md RC3).
-- Block 2: Aggregates monthly/tag-cost RTU rows (monthly_cost_type IS NOT NULL)
--   without a base-row JOIN since these are synthetic cost rows.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id

-- Step 1: Delete ALL existing cost model rows (usage + monthly + tag)
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}}
  AND cost_model_rate_type IS NOT NULL
  AND cost_model_rate_type IN ('Infrastructure', 'Supplementary');

-- Step 2: INSERT usage-cost aggregation (monthly_cost_type IS NULL)
--
-- No JOIN back to the daily summary: resource_id, persistentvolume,
-- storageclass, and all capacity columns are read directly from RatesToUsage,
-- which insert_usage_rates_to_usage.sql denormalizes onto every usage-cost
-- row at insert time (see Option C in risk-register.md RC3).
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
    MAX(rtu.resource_id),
    rtu.usage_start,
    rtu.usage_start + interval '1 day' AS usage_end,
    rtu.data_source,
    rtu.source_uuid,
    rtu.persistentvolumeclaim,
    MAX(rtu.persistentvolume),
    MAX(rtu.storageclass),
    MIN(rtu.pod_labels::text)::jsonb AS pod_labels,
    MIN(rtu.volume_labels::text)::jsonb AS volume_labels,
    MIN(rtu.all_labels::text)::jsonb AS all_labels,
    MAX(rtu.node_capacity_cpu_cores),
    MAX(rtu.node_capacity_cpu_core_hours),
    MAX(rtu.node_capacity_memory_gigabytes),
    MAX(rtu.node_capacity_memory_gigabyte_hours),
    MAX(rtu.cluster_capacity_cpu_core_hours),
    MAX(rtu.cluster_capacity_memory_gigabyte_hours),
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

-- Step 3: INSERT monthly/tag-cost aggregation (monthly_cost_type IS NOT NULL)
-- These are synthetic cost rows that don't need base-row capacity columns.
--
-- raw_currency is set to cost_model_currency for distribution rows
-- (unattributed_network, unattributed_storage) when infra costs were
-- currency-converted.  When source infra rows have raw_currency IS NULL
-- (common for OCP-on-cloud), cost_model_currency is passed as NULL so
-- the API applies the same default exchange rate (1) as the original rows.
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid, report_period_id, cluster_id, cluster_alias, namespace, node,
    usage_start, usage_end, data_source, source_uuid,
    persistentvolumeclaim,
    pod_labels, volume_labels, all_labels,
    cost_category_id, cost_model_rate_type,
    cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
    cost_model_gpu_cost,
    distributed_cost,
    monthly_cost_type,
    raw_currency
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
    SUM(CASE WHEN rtu.metric_type = 'gpu'     THEN rtu.calculated_cost ELSE 0 END),
    SUM(COALESCE(rtu.distributed_cost, 0)),
    rtu.monthly_cost_type,
    CASE WHEN rtu.monthly_cost_type IN ('unattributed_network', 'unattributed_storage')
         THEN {{cost_model_currency}}
         ELSE NULL
    END
FROM {{schema | sqlsafe}}.rates_to_usage rtu
WHERE rtu.usage_start >= {{start_date}}
  AND rtu.usage_start <= {{end_date}}
  AND rtu.source_uuid = {{source_uuid}}
  AND rtu.report_period_id = {{report_period_id}}
  AND rtu.monthly_cost_type IS NOT NULL
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
    rtu.cost_model_rate_type,
    rtu.monthly_cost_type;
