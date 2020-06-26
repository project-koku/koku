DROP INDEX IF EXISTS azure_cost_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_azure_cost_summary;

CREATE MATERIALIZED VIEW reporting_azure_cost_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, source_uuid) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        source_uuid
    FROM reporting_azurecostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX azure_cost_summary
ON reporting_azure_cost_summary (usage_start, source_uuid)
;
