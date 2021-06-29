DROP INDEX IF EXISTS ocp_cost_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocp_cost_summary;

CREATE MATERIALIZED VIEW reporting_ocp_cost_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, cluster_alias) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        cluster_alias,
        json_build_object(
            'cpu', sum((supplementary_usage_cost->>'cpu')::decimal),
            'memory', sum((supplementary_usage_cost->>'memory')::decimal),
            'storage', sum((supplementary_usage_cost->>'storage')::decimal)
        ) as supplementary_usage_cost,
        json_build_object(
            'cpu', sum((infrastructure_usage_cost->>'cpu')::decimal),
            'memory', sum((infrastructure_usage_cost->>'memory')::decimal),
            'storage', sum((infrastructure_usage_cost->>'storage')::decimal)
        ) as infrastructure_usage_cost,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        json_build_object(
            'cpu', sum(((coalesce(supplementary_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(supplementary_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(supplementary_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as supplementary_monthly_cost,
        json_build_object(
            'cpu', sum(((coalesce(infrastructure_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(infrastructure_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(infrastructure_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as infrastructure_monthly_cost,
        source_uuid
    FROM reporting_ocpusagelineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, cluster_id, cluster_alias, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocp_cost_summary
ON reporting_ocp_cost_summary (usage_start, cluster_id, cluster_alias, source_uuid)
;
