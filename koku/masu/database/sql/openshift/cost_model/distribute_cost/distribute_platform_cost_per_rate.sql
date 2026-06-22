-- Per-rate platform cost distribution via rates_to_usage.
-- Reads per-rate costs from RTU (Platform category), distributes
-- proportionally to non-Platform namespaces by CPU/memory hours,
-- writes distributed rows back to RTU with monthly_cost_type = 'platform_distributed'.
--
-- Infrastructure costs (OCP-on-cloud matching) live in daily_summary, not RTU.
-- They are distributed proportionally across rates via a scaling factor so
-- Platform namespaces fully zero out (infra + cost_model = 0).
WITH platform_rtu_cost AS (
    SELECT
        rtu.usage_start,
        rtu.source_uuid,
        rtu.cluster_id,
        rtu.custom_name,
        rtu.metric_type,
        rtu.cost_model_rate_type,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS rate_cost
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
        ON rtu.cost_category_id = cat.id
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.report_period_id = {{report_period_id}}
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND cat.name = 'Platform'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
platform_infra AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        ) AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND cat.name = 'Platform'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id
),
platform_total_rate AS (
    SELECT
        usage_start,
        cluster_id,
        SUM(rate_cost) AS total_rate_cost
    FROM platform_rtu_cost
    GROUP BY usage_start, cluster_id
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
        AND lids.namespace != 'Worker unallocated'
        AND lids.namespace != 'Storage unattributed'
        AND lids.namespace != 'Network unattributed'
        AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
        AND lids.data_source = 'Pod'
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
        AND lids.namespace != 'Worker unallocated'
        AND lids.namespace != 'Storage unattributed'
        AND lids.namespace != 'Network unattributed'
        AND (lids.cost_category_id IS NULL OR cat.name != 'Platform')
        AND lids.data_source = 'Pod'
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
    pc.source_uuid,
    nu.usage_start,
    nu.usage_start,
    nu.cluster_id,
    nu.cluster_alias,
    nu.namespace,
    nu.node,
    nu.cost_category_id,
    COALESCE(pc.custom_name, ''),
    pc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN {{distribution}} = 'cpu' THEN
        CASE WHEN d.usage_cpu_sum <= 0 THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * pc.rate_cost
                  * CASE WHEN pt.total_rate_cost > 0
                         THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                         ELSE 1 END
        END
    ELSE
        CASE WHEN d.usage_memory_sum <= 0 THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * pc.rate_cost
                  * CASE WHEN pt.total_rate_cost > 0
                         THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                         ELSE 1 END
        END
    END
FROM platform_rtu_cost pc
JOIN denominator d
    ON d.usage_start = pc.usage_start AND d.cluster_id = pc.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = pc.usage_start AND nu.cluster_id = pc.cluster_id
LEFT JOIN platform_infra pi
    ON pi.usage_start = pc.usage_start AND pi.cluster_id = pc.cluster_id
LEFT JOIN platform_total_rate pt
    ON pt.usage_start = pc.usage_start AND pt.cluster_id = pc.cluster_id
WHERE CASE WHEN {{distribution}} = 'cpu' THEN
          CASE WHEN d.usage_cpu_sum <= 0 THEN 0
               ELSE (nu.ns_cpu / d.usage_cpu_sum) * pc.rate_cost
                    * CASE WHEN pt.total_rate_cost > 0
                           THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                           ELSE 1 END
          END
      ELSE
          CASE WHEN d.usage_memory_sum <= 0 THEN 0
               ELSE (nu.ns_memory / d.usage_memory_sum) * pc.rate_cost
                    * CASE WHEN pt.total_rate_cost > 0
                           THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                           ELSE 1 END
          END
      END != 0;

-- Negate source: for each Platform namespace, negate its cost-model total plus
-- infrastructure costs from daily_summary. This ensures each Platform namespace
-- fully zeroes out in the API's cost.total computation.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace,
    cost_category_id, custom_name, metric_type, cost_model_rate_type,
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
    rtu_agg.namespace,
    rtu_agg.cost_category_id,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -(rtu_agg.cost_model_total + COALESCE(pi_ns.infra_total, 0))
FROM (
    SELECT
        rtu.report_period_id,
        rtu.source_uuid,
        rtu.usage_start,
        rtu.cluster_id,
        rtu.namespace,
        MAX(rtu.cluster_alias) AS cluster_alias,
        MAX(rtu.cost_category_id) AS cost_category_id,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS cost_model_total
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
        ON rtu.cost_category_id = cat.id
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.report_period_id = {{report_period_id}}
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND cat.name = 'Platform'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.report_period_id, rtu.source_uuid, rtu.usage_start,
             rtu.cluster_id, rtu.namespace
) rtu_agg
LEFT JOIN (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        lids.namespace,
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        ) AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
        ON lids.cost_category_id = cat.id
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND cat.name = 'Platform'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id, lids.namespace
) pi_ns
    ON pi_ns.usage_start = rtu_agg.usage_start
    AND pi_ns.cluster_id = rtu_agg.cluster_id
    AND pi_ns.namespace = rtu_agg.namespace
WHERE EXISTS (
    SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage dist
    WHERE dist.monthly_cost_type = {{cost_model_rate_type}}
    AND dist.source_uuid = rtu_agg.source_uuid
    AND dist.usage_start = rtu_agg.usage_start
    AND dist.cluster_id = rtu_agg.cluster_id
)
AND (rtu_agg.cost_model_total + COALESCE(pi_ns.infra_total, 0)) != 0;
