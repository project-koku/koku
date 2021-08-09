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
        max(source_uuid::text)::uuid as source_uuid,
        service_id,
        service_alias,
        invoice_month
    FROM reporting_gcpcostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE service_alias LIKE '%Network%'
        OR service_alias LIKE '%VPC%'
        OR service_alias LIKE '%Firewall%'
        OR service_alias LIKE '%Route%'
        OR service_alias LIKE '%IP%'
        OR service_alias LIKE '%DNS%'
        OR service_alias LIKE '%CDN%'
        OR service_alias LIKE '%NAT%'
        OR service_alias LIKE '%Traffic Director%'
        OR service_alias LIKE '%Service Discovery%'
        OR service_alias LIKE '%Cloud Domains%'
        OR service_alias LIKE '%Private Service Connect%'
        OR service_alias LIKE '%Cloud Armor%'
        AND usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, account_id, service_id, service_alias, invoice_month
)
WITH DATA
;

CREATE UNIQUE INDEX gcp_network_summary
ON reporting_gcp_network_summary (usage_start, account_id, service_id, service_alias, invoice_month)
;
