DROP INDEX IF EXISTS azure_network_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_azure_network_summary;

CREATE MATERIALIZED VIEW reporting_azure_network_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, subscription_guid, service_name) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        subscription_guid,
        service_name,
        sum(usage_quantity) as usage_quantity,
        max(unit_of_measure) as unit_of_measure,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_azurecostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE service_name IN ('Virtual Network','VPN','DNS','Traffic Manager','ExpressRoute','Load Balancer','Application Gateway')
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, subscription_guid, service_name
)
WITH DATA
;

CREATE UNIQUE INDEX azure_network_summary
ON reporting_azure_network_summary (usage_start, subscription_guid, service_name)
;
