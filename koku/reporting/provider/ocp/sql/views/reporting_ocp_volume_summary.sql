DROP INDEX IF EXISTS ocp_volume_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocp_volume_summary;

CREATE MATERIALIZED VIEW reporting_ocp_volume_summary AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, cluster_alias) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        cluster_alias,
        max(data_source) as data_source,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        json_build_object(
            'cpu', sum((supplementary_usage_cost->>'cpu')::decimal),
            'memory', sum((supplementary_usage_cost->>'memory')::decimal),
            'storage', sum((supplementary_usage_cost->>'storage')::decimal)
        ) as supplementary_usage_cost,
        json_build_object(
            'cpu', sum((infrastructure_usage_cost->>'cpu')::decimal),
            'memory', sum((infrastructure_usage_cost->>'memory')::decimal),
            'storage', sum((infrastructure_usage_cost->>'storage')::decimal)
        ) as infrastructure_usage_cost,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        sum(persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
        sum(volume_request_storage_gigabyte_months) as volume_request_storage_gigabyte_months,
        sum(persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
        source_uuid
    FROM reporting_ocpusagelineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date AND data_source = 'Storage'
    GROUP BY usage_start, cluster_id, cluster_alias, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocp_volume_summary
ON reporting_ocp_volume_summary (usage_start, cluster_id, cluster_alias, source_uuid)
;
