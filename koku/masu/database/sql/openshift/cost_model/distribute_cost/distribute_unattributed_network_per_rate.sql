-- Per-rate unattributed network cost distribution via rates_to_usage.
-- Reads per-rate costs from RTU (Network unattributed namespace), distributes
-- proportionally to non-Network namespaces by CPU/memory hours (cross-cluster, daily),
-- writes distributed rows back to RTU with monthly_cost_type = 'unattributed_network'.
WITH network_rtu_cost AS (
    SELECT
        rtu.usage_start,
        rtu.source_uuid,
        rtu.cluster_id,
        rtu.custom_name,
        rtu.metric_type,
        rtu.cost_model_rate_type,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS rate_cost
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.report_period_id = {{report_period_id}}
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.namespace = 'Network unattributed'
        AND rtu.monthly_cost_type IS NULL
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
denominator AS (
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
    GROUP BY lids.usage_start, lids.cluster_id
),
namespace_usage AS (
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
    GROUP BY lids.usage_start, lids.cluster_id, lids.namespace, lids.node
)
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    cost_category_id, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost
)
SELECT
    uuid_generate_v4(),
    nu.report_period_id,
    nc.source_uuid,
    nu.usage_start,
    nu.usage_start,
    nu.cluster_id,
    nu.cluster_alias,
    nu.namespace,
    nu.node,
    nu.cost_category_id,
    nc.custom_name,
    nc.metric_type,
    nc.cost_model_rate_type,
    {{cost_model_rate_type}},
    CASE WHEN {{distribution}} = 'cpu' THEN
        CASE WHEN d.usage_cpu_sum <= 0 THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * nc.rate_cost
        END
    ELSE
        CASE WHEN d.usage_memory_sum <= 0 THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * nc.rate_cost
        END
    END
FROM network_rtu_cost nc
JOIN denominator d
    ON d.usage_start = nc.usage_start AND d.cluster_id = nc.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = nc.usage_start AND nu.cluster_id = nc.cluster_id
WHERE CASE WHEN {{distribution}} = 'cpu' THEN
          CASE WHEN d.usage_cpu_sum <= 0 THEN 0
               ELSE (nu.ns_cpu / d.usage_cpu_sum) * nc.rate_cost
          END
      ELSE
          CASE WHEN d.usage_memory_sum <= 0 THEN 0
               ELSE (nu.ns_memory / d.usage_memory_sum) * nc.rate_cost
          END
      END != 0;
