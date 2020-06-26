DROP INDEX IF EXISTS ocpall_cost_summary_account;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpall_cost_summary_by_account;

CREATE MATERIALIZED VIEW reporting_ocpall_cost_summary_by_account AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, usage_account_id) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpallcostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, usage_account_id
)
WITH DATA
;

CREATE UNIQUE INDEX ocpall_cost_summary_account
ON reporting_ocpall_cost_summary_by_account (usage_start, cluster_id, usage_account_id)
;
