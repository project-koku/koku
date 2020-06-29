DROP INDEX IF EXISTS ocpazure_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_compute_summary;

CREATE MATERIALIZED VIEW reporting_ocpazure_compute_summary AS(
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, cluster_id, subscription_guid, instance_type, resource_id) AS id,
        usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        subscription_guid,
        instance_type,
        resource_id,
        sum(usage_quantity) as usage_quantity,
        max(unit_of_measure) as unit_of_measure,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        AND instance_type IS NOT NULL
    GROUP BY usage_start, cluster_id, subscription_guid, instance_type, resource_id
)
WITH DATA
;

CREATE UNIQUE INDEX ocpazure_compute_summary
    ON reporting_ocpazure_compute_summary (usage_start, cluster_id, subscription_guid, instance_type, resource_id)
;
