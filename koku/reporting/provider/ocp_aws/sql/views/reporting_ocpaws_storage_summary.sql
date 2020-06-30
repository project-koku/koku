DROP INDEX IF EXISTS ocpaws_storage_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpaws_storage_summary;

CREATE MATERIALIZED VIEW reporting_ocpaws_storage_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, usage_account_id, product_family) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        product_family,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpawscostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE product_family LIKE '%Storage%'
        AND unit = 'GB-Mo'
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, usage_account_id, product_family
)
WITH DATA
;

CREATE UNIQUE INDEX ocpaws_storage_summary
ON reporting_ocpaws_storage_summary (usage_start, cluster_id, usage_account_id, product_family)
;
