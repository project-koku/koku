-- Per-rate worker unallocated cost distribution via rates_to_usage.
-- Reads per-rate costs from RTU (Worker unallocated namespace), distributes
-- proportionally to non-Worker namespaces by CPU/memory hours (Pod data_source),
-- writes distributed rows back to RTU with monthly_cost_type = 'worker_distributed'.
--
-- Infrastructure costs (OCP-on-cloud matching) live in daily_summary, not RTU.
-- They are distributed proportionally across rates via a scaling factor so the
-- Worker unallocated namespace fully zeroes out (infra + cost_model = 0).
WITH worker_rtu_cost AS (
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
        AND rtu.namespace = 'Worker unallocated'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
worker_infra AS (
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
        AND lids.namespace = 'Worker unallocated'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id
),
worker_total_rate AS (
    SELECT
        usage_start,
        cluster_id,
        SUM(rate_cost) AS total_rate_cost
    FROM worker_rtu_cost
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
    monthly_cost_type, distributed_cost, cost_model_id
)
SELECT
    uuid_generate_v4(),
    nu.report_period_id,
    wc.source_uuid,
    nu.usage_start,
    nu.usage_start,
    nu.cluster_id,
    nu.cluster_alias,
    nu.namespace,
    nu.node,
    nu.cost_category_id,
    COALESCE(wc.custom_name, ''),
    wc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN {{distribution}} = 'cpu' THEN
        CASE WHEN d.usage_cpu_sum <= 0 THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * wc.rate_cost
                  * CASE WHEN wt.total_rate_cost > 0
                         THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                         ELSE 1 END
        END
    ELSE
        CASE WHEN d.usage_memory_sum <= 0 THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * wc.rate_cost
                  * CASE WHEN wt.total_rate_cost > 0
                         THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                         ELSE 1 END
        END
    END,
    {{cost_model_id}}::uuid
FROM worker_rtu_cost wc
JOIN denominator d
    ON d.usage_start = wc.usage_start AND d.cluster_id = wc.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = wc.usage_start AND nu.cluster_id = wc.cluster_id
LEFT JOIN worker_infra wi
    ON wi.usage_start = wc.usage_start AND wi.cluster_id = wc.cluster_id
LEFT JOIN worker_total_rate wt
    ON wt.usage_start = wc.usage_start AND wt.cluster_id = wc.cluster_id
WHERE CASE WHEN {{distribution}} = 'cpu' THEN
          CASE WHEN d.usage_cpu_sum <= 0 THEN 0
               ELSE (nu.ns_cpu / d.usage_cpu_sum) * wc.rate_cost
                    * CASE WHEN wt.total_rate_cost > 0
                           THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                           ELSE 1 END
          END
      ELSE
          CASE WHEN d.usage_memory_sum <= 0 THEN 0
               ELSE (nu.ns_memory / d.usage_memory_sum) * wc.rate_cost
                    * CASE WHEN wt.total_rate_cost > 0
                           THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                           ELSE 1 END
          END
      END != 0;

-- Negate source: per-node negation of Worker unallocated costs.
-- Computes per-node cost-model total from source RTU + per-node infrastructure
-- from daily_summary, matching legacy per-node granularity to avoid NULL node
-- ("No-node") entries in the API.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost, cost_model_id
)
SELECT
    uuid_generate_v4(),
    src.report_period_id,
    src.source_uuid,
    src.usage_start,
    src.usage_start,
    src.cluster_id,
    src.cluster_alias,
    'Worker unallocated',
    src.node,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -(src.cost_model_total + COALESCE(infra.infra_total, 0)),
    {{cost_model_id}}::uuid
FROM (
    SELECT
        MAX(rtu.report_period_id) AS report_period_id,
        rtu.source_uuid,
        rtu.usage_start,
        rtu.cluster_id,
        rtu.node,
        MAX(rtu.cluster_alias) AS cluster_alias,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS cost_model_total
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.namespace = 'Worker unallocated'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.source_uuid, rtu.usage_start, rtu.cluster_id, rtu.node
) src
LEFT JOIN (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        ) AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace = 'Worker unallocated'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id, lids.node
) infra
    ON src.usage_start = infra.usage_start
    AND src.cluster_id = infra.cluster_id
    AND src.node IS NOT DISTINCT FROM infra.node
WHERE EXISTS (
    SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage dist
    WHERE dist.monthly_cost_type = {{cost_model_rate_type}}
    AND dist.source_uuid = src.source_uuid
    AND dist.usage_start = src.usage_start
    AND dist.cluster_id = src.cluster_id
)
AND (src.cost_model_total + COALESCE(infra.infra_total, 0)) != 0;
