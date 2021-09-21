DROP INDEX IF EXISTS gcp_storage_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_storage_summary;

CREATE MATERIALIZED VIEW reporting_gcp_storage_summary AS (
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, source_uuid) AS id,
        usage_start,
        usage_start as usage_end,
        sum(usage_amount) as usage_amount,
        MAX(unit) AS unit,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        MAX(currency) AS currency,
        source_uuid,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
        AND service_alias IN ('Filestore', 'Storage', 'Cloud Storage', 'Data Transfer')
    GROUP BY usage_start, source_uuid, invoice_month
)
WITH DATA
    ;

CREATE UNIQUE INDEX gcp_storage_summary
    ON reporting_gcp_storage_summary (usage_start, source_uuid, invoice_month)
;
