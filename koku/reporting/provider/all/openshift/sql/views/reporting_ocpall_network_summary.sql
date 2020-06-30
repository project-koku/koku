DROP INDEX IF EXISTS ocpall_network_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpall_network_summary;

CREATE MATERIALIZED VIEW reporting_ocpall_network_summary AS (
    SELECT row_number() OVER (ORDER BY usage_start, cluster_id, usage_account_id, product_code) AS id,
        lids.cluster_id,
        max(lids.cluster_alias) as cluster_alias,
        lids.usage_account_id,
        max(lids.account_alias_id) as account_alias_id,
        lids.usage_start,
        lids.usage_start as usage_end,
        lids.product_code,
        sum(lids.usage_amount) as usage_amount,
        max(lids.unit) as unit,
        sum(lids.unblended_cost) as unblended_cost,
        sum(lids.markup_cost) as markup_cost,
        max(lids.currency_code) as currency_code,
        max(lids.source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpallcostlineitem_daily_summary lids
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        AND product_code IN ('AmazonVPC','AmazonCloudFront','AmazonRoute53','AmazonAPIGateway','Virtual Network','VPN','DNS','Traffic Manager','ExpressRoute','Load Balancer','Application Gateway')
    GROUP BY lids.usage_start,
        lids.cluster_id,
        lids.usage_account_id,
        lids.product_code
)
WITH DATA
;

CREATE UNIQUE INDEX ocpall_network_summary
ON reporting_ocpall_network_summary (usage_start, cluster_id, usage_account_id, product_code)
;
