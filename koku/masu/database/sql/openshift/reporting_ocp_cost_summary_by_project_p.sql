DELETE FROM {{schema | sqlsafe}}.reporting_ocp_cost_summary_by_project_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_cost_summary_by_project_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    namespace,
    supplementary_usage_cost,
    infrastructure_usage_cost,
    supplementary_monthly_cost_json,
    infrastructure_monthly_cost_json,
    infrastructure_monthly_cost,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        cluster_alias,
        namespace,
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
        sum(infrastructure_project_raw_cost) as infrastructure_project_raw_cost,
        sum(infrastructure_project_markup_cost) as infrastructure_project_markup_cost,
        json_build_object(
            'cpu', sum(((coalesce(supplementary_project_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(supplementary_project_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(supplementary_project_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as supplementary_project_monthly_cost,
        sum(supplementary_monthly_cost) as supplementary_monthly_cost,
        json_build_object(
            'cpu', sum(((coalesce(infrastructure_project_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(infrastructure_project_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(infrastructure_project_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as infrastructure_project_monthly_cost,
        sum(infrastructure_monthly_cost) as infrastructure_monthly_cost,
        {{source_uuid}}::uuid as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY usage_start, cluster_id, cluster_alias, namespace
;
