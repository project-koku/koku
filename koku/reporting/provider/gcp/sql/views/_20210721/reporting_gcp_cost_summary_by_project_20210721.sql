DROP INDEX IF EXISTS gcp_cost_summary_project;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_cost_summary_by_project;

CREATE MATERIALIZED VIEW reporting_gcp_cost_summary_by_project AS(
    SELECT row_number() OVER(ORDER BY usage_start, project_id, project_name, account_id) as id,
        usage_start,
        usage_start as usage_end,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid,
        project_id,
        project_name,
        account_id,
        invoice_month
    FROM reporting_gcpcostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, project_id, project_name, account_id, invoice_month
)
WITH DATA
;

CREATE UNIQUE INDEX gcp_cost_summary_project
ON reporting_gcp_cost_summary_by_project (usage_start, project_id, project_name, account_id, invoice_month)
;
