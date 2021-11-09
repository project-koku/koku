DROP INDEX IF EXISTS aws_cost_summary_account;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_cost_summary_by_account;

CREATE MATERIALIZED VIEW reporting_aws_cost_summary_by_account AS(
    SELECT row_number() OVER(ORDER BY usage_start, usage_account_id) as id,
        usage_start,
        usage_start as usage_end,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        max(organizational_unit_id) as organizational_unit_id,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        SUM(blended_cost) AS blended_cost,
        SUM(markup_cost_blended) AS markup_cost_blended,
        SUM(savingsplan_effective_cost) AS savingsplan_effective_cost,
        SUM(markup_cost_savingsplan) AS markup_cost_savingsplan,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_awscostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, usage_account_id
)
WITH DATA
;

CREATE UNIQUE INDEX aws_cost_summary_account
ON reporting_aws_cost_summary_by_account (usage_start, usage_account_id)
;
