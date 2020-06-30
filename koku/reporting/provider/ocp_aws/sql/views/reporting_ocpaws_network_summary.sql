DROP INDEX IF EXISTS ocpaws_network_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpaws_network_summary;

CREATE MATERIALIZED VIEW reporting_ocpaws_network_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, usage_account_id, product_code) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        product_code,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpawscostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE product_code IN ('AmazonVPC','AmazonCloudFront','AmazonRoute53','AmazonAPIGateway')
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, usage_account_id, product_code
)
WITH DATA
;

CREATE UNIQUE INDEX ocpaws_network_summary
ON reporting_ocpaws_network_summary (usage_start, cluster_id, usage_account_id, product_code)
;
