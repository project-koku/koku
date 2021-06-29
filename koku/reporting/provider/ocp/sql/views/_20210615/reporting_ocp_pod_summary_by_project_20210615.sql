-- TODO: cody, in order for the supplementary_monthly_cost & infrastructure_monthly_cost
-- to not be empty I would need to set the data_source row on the monthly_cost rows I
-- adding in the ocp_report_db_accessor.py
-- I should talk to Doug & Andrew about this
DROP INDEX IF EXISTS ocp_pod_summary_by_project;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocp_pod_summary_by_project;

CREATE MATERIALIZED VIEW reporting_ocp_pod_summary_by_project AS(
    SELECT row_number() OVER(ORDER BY usage_start, cluster_id, cluster_alias, namespace) as id,
        usage_start as usage_start,
        usage_start as usage_end,
        cluster_id,
        cluster_alias,
        namespace,
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
        sum(pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
        sum(pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
        sum(pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
        max(cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        sum(pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
        sum(pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
        sum(pod_limit_memory_gigabyte_hours) as pod_limit_memory_gigabyte_hours,
        max(cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        json_build_object(
            'cpu', sum(((coalesce(supplementary_project_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(supplementary_project_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(supplementary_project_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as supplementary_monthly_cost,
        json_build_object(
            'cpu', sum(((coalesce(infrastructure_project_monthly_cost, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
            'memory', sum(((coalesce(infrastructure_project_monthly_cost, '{"memory": 0}'::jsonb))->>'memory')::decimal),
            'pvc', sum(((coalesce(infrastructure_project_monthly_cost, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
        ) as infrastructure_monthly_cost,
        source_uuid
    FROM reporting_ocpusagelineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date AND data_source = 'Pod'
    GROUP BY usage_start, cluster_id, cluster_alias, namespace, source_uuid
)
WITH DATA
;

CREATE UNIQUE INDEX ocp_pod_summary_by_project
ON reporting_ocp_pod_summary_by_project (usage_start, cluster_id, cluster_alias, namespace, source_uuid)
;
