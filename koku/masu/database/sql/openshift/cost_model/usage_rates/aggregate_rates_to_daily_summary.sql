-- aggregate_rates_to_daily_summary.sql (Phase 3/4)
--
-- Rolls up per-rate RatesToUsage rows into daily summary cost columns.
-- Runs AFTER all per-rate INSERTs (usage, monthly, tag) and AFTER
-- cost distribution (Phase 4 re-ordered: distribute -> aggregate -> markup).
--
-- Block 1: Aggregates usage-cost RTU rows (monthly_cost_type IS NULL)
--   with a base-row JOIN for capacity columns not stored in RTU.
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
WITH base AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        lids.namespace,
        lids.data_source,
        lids.persistentvolumeclaim,
        encode(sha256(decode(COALESCE(lids.pod_labels::text, '')
            || '|' || COALESCE(lids.volume_labels::text, '')
            || '|' || COALESCE(lids.all_labels::text, ''), 'escape')), 'hex') AS label_hash,
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

-- Step 3: INSERT monthly/tag-cost aggregation (monthly_cost_type IS NOT NULL)
-- These are synthetic cost rows that don't need base-row capacity columns.
--
-- For source-namespace negation rows (namespace = 'Network unattributed' or
-- 'Storage unattributed'), the distribution SQL puts -(cost_model + infra)
-- into distributed_cost. But the API multiplies infrastructure_raw_cost by
-- infra_exchange_rate (currency conversion) while distributed_cost is taken
-- as-is.  This mismatch leaves a residual of infra * (exchange_rate - 1).
--
-- Fix: split the infra portion out of distributed_cost into
-- infrastructure_raw_cost / infrastructure_markup_cost (with raw_currency)
-- so the API's exchange-rate annotation cancels the base-row infra correctly.
WITH source_ns_infra AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        lids.namespace,
        SUM(COALESCE(lids.infrastructure_raw_cost, 0)) AS infra_raw,
        SUM(COALESCE(lids.infrastructure_markup_cost, 0)) AS infra_markup,
        MAX(lids.raw_currency) AS raw_currency
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}
      AND lids.usage_start <= {{end_date}}
      AND lids.source_uuid = {{source_uuid}}
      AND lids.report_period_id = {{report_period_id}}
      AND lids.namespace IN ('Network unattributed', 'Storage unattributed')
      AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id, lids.node, lids.namespace
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid, report_period_id, cluster_id, cluster_alias, namespace, node,
    usage_start, usage_end, data_source, source_uuid,
    persistentvolumeclaim,
    pod_labels, volume_labels, all_labels,
    cost_category_id, cost_model_rate_type,
    cost_model_cpu_cost, cost_model_memory_cost, cost_model_volume_cost,
    cost_model_gpu_cost,
    infrastructure_raw_cost,
    infrastructure_markup_cost,
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
    CASE WHEN sni.infra_raw IS NOT NULL THEN -sni.infra_raw ELSE 0 END,
    CASE WHEN sni.infra_markup IS NOT NULL THEN -sni.infra_markup ELSE 0 END,
    SUM(COALESCE(rtu.distributed_cost, 0))
        + COALESCE(sni.infra_raw, 0) + COALESCE(sni.infra_markup, 0),
    rtu.monthly_cost_type,
    sni.raw_currency
FROM {{schema | sqlsafe}}.rates_to_usage rtu
LEFT JOIN source_ns_infra sni
    ON  rtu.usage_start = sni.usage_start
    AND rtu.cluster_id  = sni.cluster_id
    AND rtu.node IS NOT DISTINCT FROM sni.node
    AND rtu.namespace   = sni.namespace
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
    rtu.monthly_cost_type,
    sni.infra_raw,
    sni.infra_markup,
    sni.raw_currency;
