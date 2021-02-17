DROP INDEX IF EXISTS gcp_storage_summary_account;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_storage_summary_by_account;

CREATE MATERIALIZED VIEW reporting_gcp_storage_summary_by_account AS (
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, account_id) AS id,
        usage_start,
        usage_start as usage_end,
        SUM(case when usage_amount = 'NaN' then 0.0::numeric(24,9) else usage_amount end::numeric(24,9)) AS usage_amount,
        MAX(unit) AS unit,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        MAX(currency) AS currency,
        account_id,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
        AND line_item_type = 'storage'
    GROUP BY usage_start, account_id
)
WITH DATA
    ;

CREATE UNIQUE INDEX gcp_storage_summary_account
    ON reporting_gcp_storage_summary_by_account (usage_start, account_id)
;
