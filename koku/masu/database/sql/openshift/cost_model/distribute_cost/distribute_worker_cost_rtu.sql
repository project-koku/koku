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
        -- Exclude markup RTU rows (metric_type='markup', inserted by
        -- insert_markup_rates_to_usage.sql): their dollar amount is already
        -- included below via worker_infra's lids.infrastructure_markup_cost.
        -- Counting both would double the markup contribution to this pool.
        AND rtu.metric_type != 'markup'
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
-- denominator/namespace_usage (Pod variant) are materialized once per
-- populate_distributed_cost_sql() call by create_distribution_temp_tables.sql
-- and shared with distribute_platform_cost_per_rate.sql (Option B perf fix:
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
        CASE WHEN d.usage_cpu_sum <= 0 OR wt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * wt.total_rate_cost
                  * CASE WHEN wt.total_rate_cost > 0
                         THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                         ELSE 1 END
        END
        {% else %}
        CASE WHEN d.usage_memory_sum <= 0 OR wt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * wt.total_rate_cost
                  * CASE WHEN wt.total_rate_cost > 0
                         THEN (wt.total_rate_cost + COALESCE(wi.infra_total, 0)) / wt.total_rate_cost
                         ELSE 1 END
        END
        {% endif %}
        AS total_distributed
    FROM namespace_usage nu
    JOIN denominator d
        ON d.usage_start = nu.usage_start AND d.cluster_id = nu.cluster_id
    JOIN worker_total_rate wt
        ON wt.usage_start = nu.usage_start AND wt.cluster_id = nu.cluster_id
    LEFT JOIN worker_infra wi
        ON wi.usage_start = nu.usage_start AND wi.cluster_id = nu.cluster_id
)
-- Phase 2 (Option D perf fix): fan namespace_totals (N_namespaces rows) back
-- out to per-rate rows (N_rates x N_namespaces) via a cheap join against the
-- small worker_rtu_cost/worker_total_rate CTEs only — namespace_usage and
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
    wc.source_uuid,
    nt.usage_start,
    nt.usage_start,
    nt.cluster_id,
    nt.cluster_alias,
    nt.namespace,
    nt.node,
    nt.cost_category_id,
    COALESCE(wc.custom_name, ''),
    wc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN wt.total_rate_cost > 0 THEN nt.total_distributed * (wc.rate_cost / wt.total_rate_cost) ELSE 0 END,
    {{cost_model_id}}::uuid
FROM namespace_totals nt
JOIN worker_rtu_cost wc
    ON wc.usage_start = nt.usage_start AND wc.cluster_id = nt.cluster_id
JOIN worker_total_rate wt
    ON wt.usage_start = nt.usage_start AND wt.cluster_id = nt.cluster_id
WHERE CASE WHEN wt.total_rate_cost > 0 THEN nt.total_distributed * (wc.rate_cost / wt.total_rate_cost) ELSE 0 END != 0

UNION ALL

-- Infra-only fallback: when the cost model has zero non-markup rates for
-- Worker unallocated (e.g. a markup-only cost model), namespace_totals above
-- produces nothing (its INNER JOIN to worker_total_rate requires at least one
-- rate row), so infra_total would otherwise never be distributed. Distribute
-- it directly here. Guards: total_rate_cost IS NULL (no RTU rows) or <= 0.
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
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * wi.infra_total
    END,
    {% else %}
    CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * wi.infra_total
    END,
    {% endif %}
    {{cost_model_id}}::uuid
FROM worker_infra wi
JOIN denominator d
    ON d.usage_start = wi.usage_start AND d.cluster_id = wi.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = wi.usage_start AND nu.cluster_id = wi.cluster_id
LEFT JOIN worker_total_rate wt
    ON wt.usage_start = wi.usage_start AND wt.cluster_id = wi.cluster_id
WHERE (wt.total_rate_cost IS NULL OR wt.total_rate_cost <= 0)
AND wi.infra_total != 0
{% if distribution == 'cpu' %}
AND CASE WHEN d.usage_cpu_sum <= 0 THEN 0
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * wi.infra_total
    END != 0;
{% else %}
AND CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * wi.infra_total
    END != 0;
{% endif %}

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
        -- Exclude markup RTU rows (metric_type='markup', inserted by
        -- insert_markup_rates_to_usage.sql): their dollar amount is already
        -- included below via worker_infra's lids.infrastructure_markup_cost.
        -- Counting both would double the markup contribution to this pool.
        AND rtu.metric_type != 'markup'
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
    -- COALESCE instead of IS NOT DISTINCT FROM (Option E perf fix): node is
    -- occasionally NULL for cluster-level rows, but "= " with NULL-safe
    -- sentinels lets the planner use a regular equality (index-eligible) join
    -- instead of the non-mergejoinable IS NOT DISTINCT FROM operator.
    AND COALESCE(src.node, '') = COALESCE(infra.node, '')
WHERE EXISTS (
    SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage dist
    WHERE dist.monthly_cost_type = {{cost_model_rate_type}}
    AND dist.source_uuid = src.source_uuid
    AND dist.usage_start = src.usage_start
    AND dist.cluster_id = src.cluster_id
)
AND (src.cost_model_total + COALESCE(infra.infra_total, 0)) != 0

UNION ALL

-- Infra-only fallback negation: negate per-node infrastructure costs when no
-- cost model RTU rows exist for Worker unallocated (markup-only cost model).
-- No distribution-row guard needed: this SQL only runs when distribution is
-- enabled in the cost model (checked by populate_distributed_cost_sql).
SELECT
    uuid_generate_v4(),
    MAX(lids.report_period_id),
    {{source_uuid}}::uuid,
    lids.usage_start,
    lids.usage_start,
    lids.cluster_id,
    MAX(lids.cluster_alias),
    'Worker unallocated',
    lids.node,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -SUM(
        COALESCE(lids.infrastructure_raw_cost, 0) +
        COALESCE(lids.infrastructure_markup_cost, 0)
    ),
    {{cost_model_id}}::uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace = 'Worker unallocated'
    AND lids.cost_model_rate_type IS NULL
AND NOT EXISTS (
    SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start = lids.usage_start
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.cluster_id = lids.cluster_id
        AND rtu.namespace = 'Worker unallocated'
        -- Exclude markup RTU rows (metric_type='markup', inserted by
        -- insert_markup_rates_to_usage.sql): their dollar amount is already
        -- included below via lids.infrastructure_markup_cost.
        -- Counting both would double the markup contribution to this pool.
        AND rtu.metric_type != 'markup'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
)
GROUP BY lids.usage_start, lids.cluster_id, lids.node
HAVING SUM(
    COALESCE(lids.infrastructure_raw_cost, 0) +
    COALESCE(lids.infrastructure_markup_cost, 0)
) != 0;
