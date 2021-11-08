DROP INDEX IF EXISTS ocpaws_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpaws_compute_summary;

CREATE MATERIALIZED VIEW reporting_ocpaws_compute_summary AS(
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, cluster_id, usage_account_id, instance_type, resource_id) AS id,
        usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        instance_type,
        resource_id,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(blended_cost) as blended_cost,
        sum(savingsplan_effective_cost) as savingsplan_effective_cost,
        sum(markup_cost) as markup_cost,
        sum(markup_cost_blended) as markup_cost_blended,
        sum(markup_cost_savingsplan) as markup_cost_savingsplan,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpawscostlineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        AND instance_type IS NOT NULL
    GROUP BY usage_start, cluster_id, usage_account_id, instance_type, resource_id
)
WITH DATA
;

CREATE UNIQUE INDEX ocpaws_compute_summary
    ON reporting_ocpaws_compute_summary (usage_start, cluster_id, usage_account_id, instance_type, resource_id)
;
