DROP INDEX IF EXISTS gcp_database_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_database_summary;

CREATE MATERIALIZED VIEW reporting_gcp_database_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, account_id) as id,
        usage_start,
        usage_start as usage_end,
        account_id,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid,
        service_id,
        service_alias,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM reporting_gcpcostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE service_alias LIKE '%SQL%'
        OR service_alias LIKE '%Spanner%'
        OR service_alias LIKE '%Bigtable%'
        OR service_alias LIKE '%Firestore%'
        OR service_alias LIKE '%Firebase%'
        OR service_alias LIKE '%Memorystore%'
        OR service_alias LIKE '%MongoDB%'
        AND usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, account_id, service_id, service_alias, invoice_month
)
WITH DATA
;

CREATE UNIQUE INDEX gcp_database_summary
ON reporting_gcp_database_summary (usage_start, account_id, service_id, service_alias, invoice_month)
;
