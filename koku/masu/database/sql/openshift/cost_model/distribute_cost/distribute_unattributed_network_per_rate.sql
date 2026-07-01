-- Per-rate unattributed network cost distribution via rates_to_usage.
-- Reads per-rate costs from RTU (Network unattributed namespace), distributes
-- proportionally to non-Network namespaces by CPU/memory hours (cross-cluster, daily),
-- writes distributed rows back to RTU with monthly_cost_type = 'unattributed_network'.
--
-- Infrastructure costs (OCP-on-cloud matching) live in daily_summary, not RTU.
-- They are converted from raw_currency to cost_model_currency using
-- infra_to_cm_rate before inclusion, so distributed_cost is denominated
-- entirely in the cost model's currency.  The API's infra_exchange_rate
-- annotation converts from cost_model_currency to the user's requested currency.
--
-- Parameters (additional): infra_to_cm_rate, cost_model_currency
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
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
network_infra AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        SUM(
            COALESCE(lids.infrastructure_raw_cost, 0) +
            COALESCE(lids.infrastructure_markup_cost, 0)
        ) * {{infra_to_cm_rate}} AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace = 'Network unattributed'
        AND lids.cost_model_rate_type IS NULL
    GROUP BY lids.usage_start, lids.cluster_id
),
network_total_rate AS (
    SELECT
        usage_start,
        cluster_id,
        SUM(rate_cost) AS total_rate_cost
    FROM network_rtu_cost
    GROUP BY usage_start, cluster_id
),
-- denominator/namespace_usage (all-data-source variant) are materialized once
-- per populate_distributed_cost_sql() call by create_distribution_temp_tables.sql
-- and shared with distribute_unattributed_storage_per_rate.sql (Option B perf
-- fix: avoids re-scanning reporting_ocpusagelineitem_daily_summary per distribution type).
denominator AS (
    SELECT * FROM tmp_dist_denominator_all
),
namespace_usage AS (
    SELECT * FROM tmp_dist_namespace_usage_all
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
        CASE WHEN d.usage_cpu_sum <= 0 OR nt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_cpu / d.usage_cpu_sum) * nt.total_rate_cost
                  * CASE WHEN nt.total_rate_cost > 0
                         THEN (nt.total_rate_cost + COALESCE(ni.infra_total, 0)) / nt.total_rate_cost
                         ELSE 1 END
        END
        {% else %}
        CASE WHEN d.usage_memory_sum <= 0 OR nt.total_rate_cost IS NULL THEN 0
             ELSE (nu.ns_memory / d.usage_memory_sum) * nt.total_rate_cost
                  * CASE WHEN nt.total_rate_cost > 0
                         THEN (nt.total_rate_cost + COALESCE(ni.infra_total, 0)) / nt.total_rate_cost
                         ELSE 1 END
        END
        {% endif %}
        AS total_distributed
    FROM namespace_usage nu
    JOIN denominator d
        ON d.usage_start = nu.usage_start AND d.cluster_id = nu.cluster_id
    JOIN network_total_rate nt
        ON nt.usage_start = nu.usage_start AND nt.cluster_id = nu.cluster_id
    LEFT JOIN network_infra ni
        ON ni.usage_start = nu.usage_start AND ni.cluster_id = nu.cluster_id
)
-- Phase 2 (Option D perf fix): fan namespace_totals (N_namespaces rows) back
-- out to per-rate rows (N_rates x N_namespaces) via a cheap join against the
-- small network_rtu_cost/network_total_rate CTEs only — namespace_usage and
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
    ntot.report_period_id,
    nc.source_uuid,
    ntot.usage_start,
    ntot.usage_start,
    ntot.cluster_id,
    ntot.cluster_alias,
    ntot.namespace,
    ntot.node,
    ntot.cost_category_id,
    COALESCE(nc.custom_name, ''),
    nc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    CASE WHEN nt.total_rate_cost > 0 THEN ntot.total_distributed * (nc.rate_cost / nt.total_rate_cost) ELSE 0 END,
    {{cost_model_id}}::uuid
FROM namespace_totals ntot
JOIN network_rtu_cost nc
    ON nc.usage_start = ntot.usage_start AND nc.cluster_id = ntot.cluster_id
JOIN network_total_rate nt
    ON nt.usage_start = ntot.usage_start AND nt.cluster_id = ntot.cluster_id
WHERE CASE WHEN nt.total_rate_cost > 0 THEN ntot.total_distributed * (nc.rate_cost / nt.total_rate_cost) ELSE 0 END != 0

UNION ALL

-- Infra-only fallback: when cost model rates produce zero costs for Network
-- unattributed (no pod usage in that namespace), distribute infrastructure
-- costs directly. Guards: total_rate_cost IS NULL (no RTU rows) or <= 0.
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
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * ni.infra_total
    END,
    {% else %}
    CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * ni.infra_total
    END,
    {% endif %}
    {{cost_model_id}}::uuid
FROM network_infra ni
JOIN denominator d
    ON d.usage_start = ni.usage_start AND d.cluster_id = ni.cluster_id
JOIN namespace_usage nu
    ON nu.usage_start = ni.usage_start AND nu.cluster_id = ni.cluster_id
LEFT JOIN network_total_rate nt
    ON nt.usage_start = ni.usage_start AND nt.cluster_id = ni.cluster_id
WHERE (nt.total_rate_cost IS NULL OR nt.total_rate_cost <= 0)
AND ni.infra_total != 0
{% if distribution == 'cpu' %}
AND CASE WHEN d.usage_cpu_sum <= 0 THEN 0
         ELSE (nu.ns_cpu / d.usage_cpu_sum) * ni.infra_total
    END != 0;
{% else %}
AND CASE WHEN d.usage_memory_sum <= 0 THEN 0
         ELSE (nu.ns_memory / d.usage_memory_sum) * ni.infra_total
    END != 0;
{% endif %}

-- Negate source: per-node negation of Network unattributed costs.
-- Includes infrastructure costs from daily_summary. Per-node granularity
-- avoids NULL node ("No-node") entries in the API.
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
    'Network unattributed',
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
        AND rtu.namespace = 'Network unattributed'
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
        ) * {{infra_to_cm_rate}} AS infra_total
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
    WHERE lids.usage_start >= {{start_date}}::date
        AND lids.usage_start <= {{end_date}}::date
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace = 'Network unattributed'
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
WHERE (src.cost_model_total + COALESCE(infra.infra_total, 0)) != 0

UNION ALL

-- Infra-only fallback negation: negate per-node infrastructure costs when
-- no cost model RTU rows exist for Network unattributed (markup-only cost model).
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
    'Network unattributed',
    lids.node,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -SUM(
        COALESCE(lids.infrastructure_raw_cost, 0) +
        COALESCE(lids.infrastructure_markup_cost, 0)
    ) * {{infra_to_cm_rate}},
    {{cost_model_id}}::uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.namespace = 'Network unattributed'
    AND lids.cost_model_rate_type IS NULL
AND NOT EXISTS (
    SELECT 1 FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start = lids.usage_start
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.namespace = 'Network unattributed'
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
