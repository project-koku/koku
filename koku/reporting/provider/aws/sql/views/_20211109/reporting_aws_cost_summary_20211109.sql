DROP INDEX IF EXISTS aws_cost_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_cost_summary;

CREATE MATERIALIZED VIEW reporting_aws_cost_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, source_uuid) as id,
        usage_start,
        usage_start as usage_end,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        SUM(blended_cost) AS blended_cost,
        SUM(markup_cost_blended) AS markup_cost_blended,
        SUM(savingsplan_effective_cost) AS savingsplan_effective_cost,
        SUM(markup_cost_savingsplan) AS markup_cost_savingsplan,
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
