DROP INDEX IF EXISTS ocp_cost_summary_by_node;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocp_cost_summary_by_node;

CREATE MATERIALIZED VIEW reporting_ocp_cost_summary_by_node AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, cluster_alias, node) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        cluster_alias,
        node,
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
        sum(supplementary_monthly_cost) as supplementary_monthly_cost,
        sum(infrastructure_monthly_cost) as infrastructure_monthly_cost,
        sum(infrastructure_project_markup_cost) as infrastructure_project_markup_cost,
        sum(infrastructure_project_raw_cost) as infrastructure_project_raw_cost,
        source_uuid
    FROM reporting_ocpusagelineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, cluster_alias, node, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocp_cost_summary_by_node
ON reporting_ocp_cost_summary_by_node (usage_start, cluster_id, cluster_alias, node, source_uuid)
;
