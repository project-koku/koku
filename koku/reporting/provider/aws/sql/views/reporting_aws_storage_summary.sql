DROP INDEX IF EXISTS aws_storage_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_storage_summary;

CREATE MATERIALIZED VIEW reporting_aws_storage_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, source_uuid, product_family) as id,
        usage_start,
        usage_start as usage_end,
        product_family,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        source_uuid
    FROM reporting_awscostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE product_family LIKE '%Storage%'
        AND unit = 'GB-Mo'
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, source_uuid, product_family
)
WITH DATA
;

CREATE UNIQUE INDEX aws_storage_summary
ON reporting_aws_storage_summary (usage_start, source_uuid, product_family)
;
