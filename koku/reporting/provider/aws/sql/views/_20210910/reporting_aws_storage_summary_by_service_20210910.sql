DROP INDEX IF EXISTS aws_storage_summary_service;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_storage_summary_by_service;

CREATE MATERIALIZED VIEW reporting_aws_storage_summary_by_service AS(
    SELECT row_number() OVER(ORDER BY usage_start, usage_account_id, product_code, product_family) as id,
        usage_start,
        usage_start as usage_end,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        max(organizational_unit_id) as organizational_unit_id,
        product_code,
        product_family,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(blended_cost) as blended_cost,
        sum(savingsplan_effective_cost) as savingsplan_effective_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_awscostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE product_family LIKE '%Storage%'
        AND unit = 'GB-Mo'
        AND usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, usage_account_id, product_code, product_family
)
WITH DATA
;

CREATE UNIQUE INDEX aws_storage_summary_service
ON reporting_aws_storage_summary_by_service (usage_start, usage_account_id, product_code, product_family)
;
