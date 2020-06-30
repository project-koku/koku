DROP INDEX IF EXISTS ocpazure_cost_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_cost_summary;

CREATE MATERIALIZED VIEW reporting_ocpazure_cost_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, source_uuid) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocpazure_cost_summary
ON reporting_ocpazure_cost_summary (usage_start, cluster_id, cluster_alias, source_uuid)
;
