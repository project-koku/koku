DROP INDEX IF EXISTS gcp_cost_summary_region;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_region;

CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_region AS(
    SELECT row_number() OVER(ORDER BY usage_start, account_id, region) as id,
        usage_start,
        usage_start as usage_end,
        account_id,
        region,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid,
        invoice_month
    FROM reporting_gcpcostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, account_id, region, invoice_month
)
WITH DATA
;

CREATE UNIQUE INDEX gcp_cost_summary_region
ON reporting_gcp_cost_summary_by_region (usage_start, account_id, region, invoice_month)
;
