-- estimate_rates_to_usage_rows.sql (R3 Risk Assessment)
--
-- Estimates the number of rows cost_model_rates_to_usage would produce
-- from the current daily summary data for a 30-day window.
--
-- RatesToUsage groups at (usage_start, cluster_id, node, namespace,
-- data_source, cost_category_id) — coarser than the daily summary.
-- Each group produces up to 12 rows (one per non-zero rate component
-- for usage costs) plus additional rows for monthly costs, tag costs,
-- and markup.
--
-- Run against a production-like schema to get concrete numbers.
-- Replace {{schema}} with the actual tenant schema name.

-- Part 1: Usage cost row estimation
-- Each coarse-grained group × 12 rate components = max RatesToUsage rows
-- (in practice, most cost models set 3-5 rates, so multiply by actual rate count)
SELECT
    'usage_cost_groups' AS metric,
    count(*) AS daily_summary_rows,
    count(DISTINCT (
        usage_start::text,
        cluster_id,
        coalesce(node, ''),
        coalesce(namespace, ''),
        coalesce(data_source, ''),
        coalesce(cost_category_id::text, '')
    )) AS coarse_groups,
    count(DISTINCT (
        usage_start::text,
        cluster_id,
        coalesce(node, ''),
        coalesce(namespace, ''),
        coalesce(data_source, ''),
        coalesce(cost_category_id::text, '')
    )) * 12 AS max_rtu_rows_all_rates,
    count(DISTINCT (
        usage_start::text,
        cluster_id,
        coalesce(node, ''),
        coalesce(namespace, ''),
        coalesce(data_source, ''),
        coalesce(cost_category_id::text, '')
    )) * 5 AS estimated_rtu_rows_typical
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= now() - interval '30 days'
    AND (cost_model_rate_type IS NULL
         OR cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
    AND monthly_cost_type IS NULL
    AND namespace IS NOT NULL
;

-- Part 2: Monthly cost row estimation
-- Each monthly cost SQL produces 1 RatesToUsage row per existing daily summary row
SELECT
    'monthly_cost_groups' AS metric,
    count(*) AS monthly_cost_rows,
    count(DISTINCT monthly_cost_type) AS distinct_monthly_types
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= now() - interval '30 days'
    AND monthly_cost_type IS NOT NULL
    AND cost_model_rate_type IN ('Infrastructure', 'Supplementary')
;

-- Part 3: Tag cost row estimation
SELECT
    'tag_cost_groups' AS metric,
    count(*) AS tag_cost_rows
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= now() - interval '30 days'
    AND monthly_cost_type = 'Tag'
;

-- Part 4: Distribution row estimation (for the breakdown table, not RatesToUsage)
SELECT
    'distribution_rows' AS metric,
    cost_model_rate_type,
    count(*) AS row_count
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= now() - interval '30 days'
    AND cost_model_rate_type IN (
        'platform_distributed', 'worker_distributed',
        'unattributed_storage', 'unattributed_network', 'gpu_distributed'
    )
    AND distributed_cost IS NOT NULL
    AND distributed_cost != 0
GROUP BY cost_model_rate_type
;

-- Part 5: Summary — total estimated RatesToUsage + Breakdown rows
WITH usage_groups AS (
    SELECT count(DISTINCT (
        usage_start::text,
        cluster_id,
        coalesce(node, ''),
        coalesce(namespace, ''),
        coalesce(data_source, ''),
        coalesce(cost_category_id::text, '')
    )) AS cnt
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= now() - interval '30 days'
        AND (cost_model_rate_type IS NULL
             OR cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
        AND monthly_cost_type IS NULL
        AND namespace IS NOT NULL
),
monthly AS (
    SELECT count(*) AS cnt
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= now() - interval '30 days'
        AND monthly_cost_type IS NOT NULL
        AND cost_model_rate_type IN ('Infrastructure', 'Supplementary')
),
tag AS (
    SELECT count(*) AS cnt
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= now() - interval '30 days'
        AND monthly_cost_type = 'Tag'
),
dist AS (
    SELECT count(*) AS cnt
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= now() - interval '30 days'
        AND cost_model_rate_type IN (
            'platform_distributed', 'worker_distributed',
            'unattributed_storage', 'unattributed_network', 'gpu_distributed'
        )
        AND distributed_cost IS NOT NULL
        AND distributed_cost != 0
)
SELECT
    'TOTALS (30 days)' AS label,
    ug.cnt AS usage_coarse_groups,
    ug.cnt * 12 AS max_rtu_usage_rows,
    ug.cnt * 5 AS est_rtu_usage_rows_typical,
    m.cnt AS rtu_monthly_rows,
    t.cnt AS rtu_tag_rows,
    (ug.cnt * 5) + m.cnt + t.cnt AS est_total_rtu_rows,
    (ug.cnt * 12) + m.cnt + t.cnt AS max_total_rtu_rows,
    d.cnt AS breakdown_distribution_rows,
    (ug.cnt * 5) + m.cnt + t.cnt + d.cnt AS est_total_breakdown_leaf_rows
FROM usage_groups ug, monthly m, tag t, dist d
;
