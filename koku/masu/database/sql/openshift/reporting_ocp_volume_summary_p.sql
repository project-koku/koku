DELETE FROM {{schema | sqlsafe}}.reporting_ocp_volume_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_volume_summary_p (
    id,
    cluster_id,
    cluster_alias,
    resource_ids,
    resource_count,
    data_source,
    usage_start,
    usage_end,
    infrastructure_raw_cost,
    infrastructure_usage_cost,
    infrastructure_markup_cost,
    infrastructure_monthly_cost_json,
    supplementary_usage_cost,
    supplementary_monthly_cost_json,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    persistentvolumeclaim_capacity_gigabyte_months,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        max(data_source) as data_source,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        json_build_object(
            'cpu', sum((infrastructure_usage_cost->>'cpu')::decimal),
            'memory', sum((infrastructure_usage_cost->>'memory')::decimal),
            'storage', sum((infrastructure_usage_cost->>'storage')::decimal)
        ) as infrastructure_usage_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        json_build_object(
            'cpu', sum(((coalesce(infrastructure_monthly_cost_json, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(infrastructure_monthly_cost_json, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(infrastructure_monthly_cost_json, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as infrastructure_monthly_cost_json,
        json_build_object(
            'cpu', sum((supplementary_usage_cost->>'cpu')::decimal),
            'memory', sum((supplementary_usage_cost->>'memory')::decimal),
            'storage', sum((supplementary_usage_cost->>'storage')::decimal)
        ) as supplementary_usage_cost,
        json_build_object(
            'cpu', sum(((coalesce(supplementary_monthly_cost_json, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(supplementary_monthly_cost_json, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(supplementary_monthly_cost_json, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as supplementary_monthly_cost_json,
        sum(volume_request_storage_gigabyte_months) as volume_request_storage_gigabyte_months,
        sum(persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
        sum(persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
        {{source_uuid}}::uuid as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Storage'
    GROUP BY usage_start, cluster_id, cluster_alias
;
