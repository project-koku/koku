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
        -- Exclude markup RTU rows (metric_type='markup', inserted by
        -- insert_markup_rates_to_usage.sql): their dollar amount is already
        -- included below via platform_infra's lids.infrastructure_markup_cost.
        -- Counting both would double the markup contribution to this pool.
        AND rtu.metric_type != 'markup'
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
-- denominator/namespace_usage (Pod variant) are materialized once per
-- populate_distributed_cost_sql() call by create_distribution_temp_tables.sql
-- and shared with distribute_worker_cost_per_rate.sql (Option B perf fix:
-- avoids re-scanning reporting_ocpusagelineitem_daily_summary per distribution type).
denominator AS (
    SELECT * FROM tmp_dist_denominator_pod
),
namespace_usage AS (
    SELECT * FROM tmp_dist_namespace_usage_pod
),
-- Phase 1 (Option D perf fix, RC1 row amplification): compute each
-- namespace's TOTAL distributed cost exactly once (N_namespaces rows), doing
-- the expensive join against namespace_usage/denominator a single time
-- instead of once per rate. Mathematically identical to the pre-Option-D
-- per-rate formula: (ns_cpu/usage_cpu_sum) * rate_cost * scaling, since
-- total_rate_cost cancels out when Phase 2 re-multiplies by
-- (rate_cost / total_rate_cost).
namespace_totals AS (
    SELECT
        nu.usage_start,
        nu.cluster_id,
        nu.namespace,
        nu.node,
        nu.report_period_id,
        nu.cluster_alias,
        nu.cost_category_id,
        {% if distribution == 'cpu' %}
        CASE WHEN d.usage_cpu_sum <= 0 OR pt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * pt.total_rate_cost
                  * CASE WHEN pt.total_rate_cost > 0
                         THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                         ELSE 1 END
        END
        {% else %}
        CASE WHEN d.usage_memory_sum <= 0 OR pt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * pt.total_rate_cost
                  * CASE WHEN pt.total_rate_cost > 0
                         THEN (pt.total_rate_cost + COALESCE(pi.infra_total, 0)) / pt.total_rate_cost
                         ELSE 1 END
        END
        {% endif %}
        AS total_distributed
    FROM namespace_usage nu
    JOIN denominator d
        ON d.usage_start = nu.usage_start AND d.cluster_id = nu.cluster_id
    JOIN platform_total_rate pt
        ON pt.usage_start = nu.usage_start AND pt.cluster_id = nu.cluster_id
    LEFT JOIN platform_infra pi
        ON pi.usage_start = nu.usage_start AND pi.cluster_id = nu.cluster_id
)
-- Phase 2 (Option D perf fix): fan namespace_totals (N_namespaces rows) back
-- out to per-rate rows (N_rates x N_namespaces) via a cheap join against the
-- small platform_rtu_cost/platform_total_rate CTEs only — namespace_usage and
-- denominator (the large, daily_summary-derived relations) are never touched
-- again here.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    cost_category_id, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost, cost_model_id
)
SELECT
    uuid_generate_v4(),
    nt.report_period_id,
    pc.source_uuid,
    nt.usage_start,
    nt.usage_start,
    nt.cluster_id,
    nt.cluster_alias,
    nt.namespace,
    nt.node,
    nt.cost_category_id,
    COALESCE(pc.custom_name, ''),
    pc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN pt.total_rate_cost > 0 THEN nt.total_distributed * (pc.rate_cost / pt.total_rate_cost) ELSE 0 END,
    {{cost_model_id}}::uuid
FROM namespace_totals nt
JOIN platform_rtu_cost pc
    ON pc.usage_start = nt.usage_start AND pc.cluster_id = nt.cluster_id
JOIN platform_total_rate pt
    ON pt.usage_start = nt.usage_start AND pt.cluster_id = nt.cluster_id
WHERE CASE WHEN pt.total_rate_cost > 0 THEN nt.total_distributed * (pc.rate_cost / pt.total_rate_cost) ELSE 0 END != 0

UNION ALL

-- Infra-only fallback: when the cost model has zero non-markup rates across
-- the *entire* Platform category for this cluster/date (e.g. a markup-only
-- cost model), namespace_totals above produces nothing (its INNER JOIN to
-- platform_total_rate requires at least one rate row), so infra_total would
-- otherwise never be distributed. Distribute it directly here. Guards:
-- total_rate_cost IS NULL (no RTU rows) or <= 0.
SELECT
    uuid_generate_v4(),
    nu.report_period_id,
    {{source_uuid}}::uuid,
    nu.usage_start,
    nu.usage_start,
    nu.cluster_id,
    nu.cluster_alias,
    nu.namespace,
    nu.node,
    nu.cost_category_id,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    {% if distribution == 'cpu' %}
    CASE WHEN d.usage_cpu_sum <= 0 THEN 0
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * pi.infra_total
    END,
    {% else %}
    CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * pi.infra_total
    END,
    {% endif %}
    {{cost_model_id}}::uuid
FROM platform_infra pi
JOIN denominator d
    ON d.usage_start = pi.usage_start AND d.cluster_id = pi.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = pi.usage_start AND nu.cluster_id = pi.cluster_id
LEFT JOIN platform_total_rate pt
    ON pt.usage_start = pi.usage_start AND pt.cluster_id = pi.cluster_id
WHERE (pt.total_rate_cost IS NULL OR pt.total_rate_cost <= 0)
AND pi.infra_total != 0
{% if distribution == 'cpu' %}
AND CASE WHEN d.usage_cpu_sum <= 0 THEN 0
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * pi.infra_total
    END != 0;
{% else %}
AND CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * pi.infra_total
    END != 0;
{% endif %}

-- Negate source: per-namespace, per-node negation for each real Platform
-- namespace. Driven from daily_summary (every real Platform namespace/node)
-- rather than from the RTU rate rows, with a LEFT JOIN to the RTU rate
-- aggregate: a namespace with real infra cost but zero non-markup RTU rows
-- (e.g. a Platform pod with no CPU/memory usage that day, or a markup-only
-- cost model) must still be negated -- otherwise its infra cost is both
-- distributed to projects (via the whole-pool total above) AND left sitting
-- on the source namespace, double-counting it. Includes infrastructure costs
-- from daily_summary. Per-node granularity avoids NULL node ("No-node")
-- entries in the API.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    cost_category_id, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost, cost_model_id
)
SELECT
    uuid_generate_v4(),
    MAX(lids.report_period_id),
    {{source_uuid}}::uuid,
    lids.usage_start,
    lids.usage_start,
    lids.cluster_id,
    MAX(lids.cluster_alias),
    lids.namespace,
    lids.node,
    MAX(lids.cost_category_id),
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -(
        COALESCE(MAX(rtu_agg.cost_model_total), 0) +
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        )
    ),
    {{cost_model_id}}::uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat
    ON lids.cost_category_id = cat.id
LEFT JOIN (
    SELECT
        rtu.source_uuid,
        rtu.usage_start,
        rtu.cluster_id,
        rtu.namespace,
        rtu.node,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS cost_model_total
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category cat2
        ON rtu.cost_category_id = cat2.id
    WHERE rtu.usage_start >= {{start_date}}::date
        AND rtu.usage_start <= {{end_date}}::date
        AND rtu.report_period_id = {{report_period_id}}
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND cat2.name = 'Platform'
        -- Exclude markup RTU rows (metric_type='markup', inserted by
        -- insert_markup_rates_to_usage.sql): their dollar amount is already
        -- included below via lids.infrastructure_markup_cost.
        -- Counting both would double the markup contribution to this pool.
        AND rtu.metric_type != 'markup'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.source_uuid, rtu.usage_start, rtu.cluster_id,
             rtu.namespace, rtu.node
) rtu_agg
    ON rtu_agg.usage_start = lids.usage_start
    AND rtu_agg.cluster_id = lids.cluster_id
    AND rtu_agg.namespace = lids.namespace
    -- COALESCE instead of IS NOT DISTINCT FROM (Option E perf fix): node is
    -- occasionally NULL for cluster-level rows, but "= " with NULL-safe
    -- sentinels lets the planner use a regular equality (index-eligible) join
    -- instead of the non-mergejoinable IS NOT DISTINCT FROM operator.
    AND COALESCE(rtu_agg.node, '') = COALESCE(lids.node, '')
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND cat.name = 'Platform'
    AND lids.cost_model_rate_type IS NULL
    AND EXISTS (
        SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage dist
        WHERE dist.monthly_cost_type = {{cost_model_rate_type}}
        AND dist.source_uuid = {{source_uuid}}::uuid
        AND dist.usage_start = lids.usage_start
        AND dist.cluster_id = lids.cluster_id
    )
GROUP BY lids.usage_start, lids.cluster_id, lids.namespace, lids.node
HAVING (
    COALESCE(MAX(rtu_agg.cost_model_total), 0) +
    SUM(
        COALESCE(lids.infrastructure_raw_cost, 0) +
        COALESCE(lids.infrastructure_markup_cost, 0)
    )
) != 0;
