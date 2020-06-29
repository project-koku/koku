DROP INDEX IF EXISTS ocpazure_cost_summary_service;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_cost_summary_by_service;

CREATE MATERIALIZED VIEW reporting_ocpazure_cost_summary_by_service AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, subscription_guid, service_name) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        subscription_guid,
        service_name,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, subscription_guid, service_name
)
WITH DATA
;

CREATE UNIQUE INDEX ocpazure_cost_summary_service
ON reporting_ocpazure_cost_summary_by_service (usage_start, cluster_id, subscription_guid, service_name)
;
