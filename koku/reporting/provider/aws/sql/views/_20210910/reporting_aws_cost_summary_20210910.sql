DROP INDEX IF EXISTS aws_cost_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_cost_summary;

CREATE MATERIALIZED VIEW reporting_aws_cost_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, source_uuid) as id,
        usage_start,
        usage_start as usage_end,
        sum(unblended_cost) as unblended_cost,
        sum(savingsplan_effective_cost) as savingsplan_effective_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        source_uuid
    FROM reporting_awscostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX aws_cost_summary
ON reporting_aws_cost_summary (usage_start, source_uuid)
;
