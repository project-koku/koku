DROP INDEX IF EXISTS ocpall_storage_summary_p;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpall_storage_summary_p;

CREATE MATERIALIZED VIEW reporting_ocpall_storage_summary_p AS (
    SELECT row_number() OVER (ORDER BY usage_start, cluster_id, usage_account_id, product_family, product_code) AS id,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        usage_start,
        usage_start as usage_end,
        product_family,
        product_code,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpallcostlineitem_daily_summary_p
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
        AND (product_family LIKE '%Storage%' OR product_code LIKE '%Storage%')
        AND unit = 'GB-Mo'
    GROUP BY usage_start,
        cluster_id,
        usage_account_id,
        product_family,
        product_code
)
WITH DATA
;

CREATE UNIQUE INDEX ocpall_storage_summary_p
ON reporting_ocpall_storage_summary_p (usage_start, cluster_id, usage_account_id, product_family, product_code)
;
