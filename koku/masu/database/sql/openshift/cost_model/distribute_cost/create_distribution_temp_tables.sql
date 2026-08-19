-- Materializes the shared denominator/namespace_usage aggregates used by
-- ALL FOUR per-rate distribution SQL files (platform, worker, unattributed
-- storage, unattributed network) for a single (schema, source_uuid,
-- report_period, date range) call.
--
-- Without this, distribute_platform_cost_per_rate.sql and
-- distribute_worker_cost_per_rate.sql each independently re-scan and
-- re-aggregate reporting_ocpusagelineitem_daily_summary with an identical
-- "Pod data_source, non-overhead namespace" GROUP BY (RC2: redundant scans),
-- and distribute_unattributed_storage_per_rate.sql /
-- distribute_unattributed_network_per_rate.sql duplicate a second,
-- "all data_source" variant of the same aggregation between themselves.
-- Materializing each variant once and having all four per-rate files read
-- from the resulting temp tables turns 4 scans into 2 per
-- populate_distributed_cost_sql() call.
--
-- Temp tables live in pg_temp and are visible regardless of search_path, so
-- they remain usable across the schema_context() switches inherent to
-- Django's per-request connection reuse. They are dropped and recreated on
-- every call (never reused across calls) to avoid stale data leaking across
-- providers/months/tenants that might share a pooled connection.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id

DROP TABLE IF EXISTS tmp_dist_denominator_pod;
DROP TABLE IF EXISTS tmp_dist_namespace_usage_pod;
DROP TABLE IF EXISTS tmp_dist_denominator_all;
DROP TABLE IF EXISTS tmp_dist_namespace_usage_all;

-- "Pod" variant: used by distribute_platform_cost_per_rate.sql and
-- distribute_worker_cost_per_rate.sql. Restricted to data_source = 'Pod'.
CREATE TEMPORARY TABLE tmp_dist_denominator_pod AS
SELECT
    lids.usage_start,
    lids.cluster_id,
    SUM(lids.pod_effective_usage_cpu_core_hours) AS usage_cpu_sum,
    SUM(lids.pod_effective_usage_memory_gigabyte_hours) AS usage_memory_sum
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
    ON lids.cost_category_id = cat.id
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace != 'Worker unallocated'
    AND lids.namespace != 'Storage unattributed'
    AND lids.namespace != 'Network unattributed'
    AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
    AND lids.data_source = 'Pod'
GROUP BY lids.usage_start, lids.cluster_id;

CREATE TEMPORARY TABLE tmp_dist_namespace_usage_pod AS
SELECT
    lids.usage_start,
    lids.cluster_id,
    lids.namespace,
    lids.node,
    MAX(lids.report_period_id) AS report_period_id,
    MAX(lids.cluster_alias) AS cluster_alias,
    MAX(lids.cost_category_id) AS cost_category_id,
    SUM(lids.pod_effective_usage_cpu_core_hours) AS ns_cpu,
    SUM(lids.pod_effective_usage_memory_gigabyte_hours) AS ns_memory
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
    ON lids.cost_category_id = cat.id
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
    AND lids.namespace != 'Worker unallocated'
    AND lids.namespace != 'Storage unattributed'
    AND lids.namespace != 'Network unattributed'
    AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
    AND lids.data_source = 'Pod'
GROUP BY lids.usage_start, lids.cluster_id, lids.namespace, lids.node;

-- "All data source" variant: used by distribute_unattributed_storage_per_rate.sql
-- and distribute_unattributed_network_per_rate.sql. Not restricted to Pod,
-- since storage/network overhead is distributed across every data_source.
CREATE TEMPORARY TABLE tmp_dist_denominator_all AS
SELECT
    lids.usage_start,
    lids.cluster_id,
    SUM(lids.pod_effective_usage_cpu_core_hours) AS usage_cpu_sum,
    SUM(lids.pod_effective_usage_memory_gigabyte_hours) AS usage_memory_sum
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
    ON lids.cost_category_id = cat.id
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace != 'Storage unattributed'
    AND lids.namespace != 'Network unattributed'
    AND lids.namespace != 'Worker unallocated'
    AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
GROUP BY lids.usage_start, lids.cluster_id;

CREATE TEMPORARY TABLE tmp_dist_namespace_usage_all AS
SELECT
    lids.usage_start,
    lids.cluster_id,
    lids.namespace,
    lids.node,
    MAX(lids.report_period_id) AS report_period_id,
    MAX(lids.cluster_alias) AS cluster_alias,
    MAX(lids.cost_category_id) AS cost_category_id,
    SUM(lids.pod_effective_usage_cpu_core_hours) AS ns_cpu,
    SUM(lids.pod_effective_usage_memory_gigabyte_hours) AS ns_memory
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
    ON lids.cost_category_id = cat.id
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace IS NOT NULL
    AND lids.namespace != 'Storage unattributed'
    AND lids.namespace != 'Network unattributed'
    AND lids.namespace != 'Worker unallocated'
    AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
GROUP BY lids.usage_start, lids.cluster_id, lids.namespace, lids.node;

CREATE INDEX ON tmp_dist_denominator_pod (usage_start, cluster_id);
CREATE INDEX ON tmp_dist_namespace_usage_pod (usage_start, cluster_id);
CREATE INDEX ON tmp_dist_denominator_all (usage_start, cluster_id);
CREATE INDEX ON tmp_dist_namespace_usage_all (usage_start, cluster_id);
