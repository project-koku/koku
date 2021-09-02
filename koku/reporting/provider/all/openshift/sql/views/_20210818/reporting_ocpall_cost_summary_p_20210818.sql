DROP INDEX IF EXISTS ocpall_cost_summary_p;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpall_cost_summary_p;

CREATE MATERIALIZED VIEW reporting_ocpall_cost_summary_p AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, source_uuid) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        source_uuid
    FROM reporting_ocpallcostlineitem_daily_summary_p
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, cluster_id, cluster_alias, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocpall_cost_summary_p
ON reporting_ocpall_cost_summary_p (usage_start, cluster_id, source_uuid)
;
