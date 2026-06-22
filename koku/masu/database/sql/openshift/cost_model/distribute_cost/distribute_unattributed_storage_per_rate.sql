-- Per-rate unattributed storage cost distribution via rates_to_usage.
-- Reads per-rate costs from RTU (Storage unattributed namespace), distributes
-- proportionally to non-Storage namespaces by CPU/memory hours (cross-cluster, daily),
-- writes distributed rows back to RTU with monthly_cost_type = 'unattributed_storage'.
WITH storage_rtu_cost AS (
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
        AND rtu.namespace = 'Storage unattributed'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
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
    sc.source_uuid,
    nu.usage_start,
    nu.usage_start,
    nu.cluster_id,
    nu.cluster_alias,
    nu.namespace,
    nu.node,
    nu.cost_category_id,
    COALESCE(sc.custom_name, ''),
    sc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN {{distribution}} = 'cpu' THEN
        CASE WHEN d.usage_cpu_sum <= 0 THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * sc.rate_cost
        END
    ELSE
        CASE WHEN d.usage_memory_sum <= 0 THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * sc.rate_cost
        END
    END
FROM storage_rtu_cost sc
JOIN denominator d
    ON d.usage_start = sc.usage_start AND d.cluster_id = sc.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = sc.usage_start AND nu.cluster_id = sc.cluster_id
WHERE CASE WHEN {{distribution}} = 'cpu' THEN
          CASE WHEN d.usage_cpu_sum <= 0 THEN 0
               ELSE (nu.ns_cpu / d.usage_cpu_sum) * sc.rate_cost
          END
      ELSE
          CASE WHEN d.usage_memory_sum <= 0 THEN 0
               ELSE (nu.ns_memory / d.usage_memory_sum) * sc.rate_cost
          END
      END != 0;

-- Negate source: offset Storage unattributed costs so the net distributed total is zero.
-- Must negate cost-model costs (from RTU) AND infrastructure/markup costs (from
-- daily_summary) so the API's cost_total + unattributed_storage sums to zero.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace,
    custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost
)
SELECT
    uuid_generate_v4(),
    rtu_agg.report_period_id,
    rtu_agg.source_uuid,
    rtu_agg.usage_start,
    rtu_agg.usage_start,
    rtu_agg.cluster_id,
    rtu_agg.cluster_alias,
    'Storage unattributed',
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -(rtu_agg.cost_model_total + COALESCE(infra_agg.infra_total, 0))
FROM (
    SELECT
        rtu.report_period_id,
        rtu.source_uuid,
        rtu.usage_start,
        rtu.cluster_id,
        MAX(rtu.cluster_alias) AS cluster_alias,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS cost_model_total
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.report_period_id = {{report_period_id}}
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.namespace = 'Storage unattributed'
        AND rtu.monthly_cost_type IS NULL
    GROUP BY rtu.report_period_id, rtu.source_uuid, rtu.usage_start,
             rtu.cluster_id
    HAVING SUM(COALESCE(rtu.calculated_cost, 0)) != 0
) rtu_agg
LEFT JOIN (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        ) AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace = 'Storage unattributed'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id
) infra_agg
    ON rtu_agg.usage_start = infra_agg.usage_start
    AND rtu_agg.cluster_id = infra_agg.cluster_id;
