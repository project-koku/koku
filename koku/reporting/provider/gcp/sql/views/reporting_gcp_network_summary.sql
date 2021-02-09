DROP INDEX IF EXISTS gcp_network_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_network_summary;

CREATE MATERIALIZED VIEW reporting_gcp_network_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, account_id) as id,
        usage_start,
        usage_start as usage_end,
        account_id,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_gcpcostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE sku_alias LIKE '%Network%'
        OR sku_alias LIKE '%VPC%'
        OR sku_alias LIKE '%Firewall%'
        OR sku_alias LIKE '%Route%'
        OR sku_alias LIKE '%IP%'
        OR sku_alias LIKE '%DNS%'
        OR sku_alias LIKE '%CDN%'
        OR sku_alias LIKE '%NAT%'
        OR sku_alias LIKE '%Traffic Director%'
        OR sku_alias LIKE '%Service Discovery%'
        OR sku_alias LIKE '%Cloud Domains%'
        OR sku_alias LIKE '%Private Service Connect$'
        OR sku_alias LIKE '%Cloud Armor%'
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, account_id
)
WITH DATA
;

CREATE UNIQUE INDEX gcp_network_summary
ON reporting_gcp_network_summary (usage_start, account_id)
;
