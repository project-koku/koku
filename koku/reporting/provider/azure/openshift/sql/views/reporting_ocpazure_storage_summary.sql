DROP INDEX IF EXISTS ocpazure_storage_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_storage_summary;

CREATE MATERIALIZED VIEW reporting_ocpazure_storage_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, subscription_guid, service_name) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        max(cluster_alias) as cluster_alias,
        subscription_guid,
        service_name,
        sum(usage_quantity) as usage_quantity,
        max(unit_of_measure) as unit_of_measure,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_ocpazurecostlineitem_daily_summary
    -- Get data for this month or last month
    WHERE service_name LIKE '%Storage%'
        AND unit_of_measure = 'GB-Mo'
        AND usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
    GROUP BY usage_start, cluster_id, subscription_guid, service_name
)
WITH DATA
;

CREATE UNIQUE INDEX ocpazure_storage_summary
ON reporting_ocpazure_storage_summary (usage_start, cluster_id, subscription_guid, service_name)
;
