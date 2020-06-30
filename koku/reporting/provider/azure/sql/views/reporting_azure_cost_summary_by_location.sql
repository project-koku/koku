DROP INDEX IF EXISTS azure_cost_summary_location;
DROP MATERIALIZED VIEW IF EXISTS reporting_azure_cost_summary_by_location;

CREATE MATERIALIZED VIEW reporting_azure_cost_summary_by_location AS(
    SELECT row_number() OVER(ORDER BY usage_start, subscription_guid, resource_location) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        subscription_guid,
        resource_location,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_azurecostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, subscription_guid, resource_location
)
WITH DATA
;

CREATE UNIQUE INDEX azure_cost_summary_location
ON reporting_azure_cost_summary_by_location (usage_start, subscription_guid, resource_location)
;
