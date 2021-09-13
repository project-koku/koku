DROP INDEX IF EXISTS gcp_compute_summary_project;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_compute_summary_by_project;

CREATE MATERIALIZED VIEW reporting_gcp_compute_summary_by_project AS (
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, instance_type, project_id, project_name, account_id) AS id,
        usage_start,
        usage_start as usage_end,
        instance_type,
        sum(usage_amount) as usage_amount,
        MAX(unit) AS unit,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        MAX(currency) AS currency,
        project_id,
        project_name,
        account_id,
        max(source_uuid::text)::uuid as source_uuid,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
        AND instance_type IS NOT NULL
    GROUP BY usage_start, instance_type, project_id, project_name, account_id, invoice_month
)
WITH DATA
    ;

CREATE UNIQUE INDEX gcp_compute_summary_project
    ON reporting_gcp_compute_summary_by_project (usage_start, instance_type, project_id, project_name, account_id, invoice_month)
;
