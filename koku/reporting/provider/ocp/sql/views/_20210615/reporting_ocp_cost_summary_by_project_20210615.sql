DROP INDEX IF EXISTS ocp_cost_summary_by_project;
DROP MATERIALIZED VIEW IF EXISTS reporting_ocp_cost_summary_by_project;

CREATE MATERIALIZED VIEW reporting_ocp_cost_summary_by_project AS(
 SELECT row_number() OVER (ORDER BY usage_start, cluster_id, cluster_alias, namespace) AS "id",
    usage_start,
    usage_start AS "usage_end",
    cluster_id,
    cluster_alias,
    namespace,
    json_build_object(
        'cpu', sum(((supplementary_usage_cost ->> 'cpu'::text))::numeric),
        'memory', sum(((supplementary_usage_cost ->> 'memory'::text))::numeric),
        'storage', sum(((supplementary_usage_cost ->> 'storage'::text))::numeric)
    ) AS "supplementary_usage_cost",
    json_build_object(
        'cpu', sum(((infrastructure_usage_cost ->> 'cpu'::text))::numeric),
        'memory', sum(((infrastructure_usage_cost ->> 'memory'::text))::numeric),
        'storage', sum(((infrastructure_usage_cost ->> 'storage'::text))::numeric)
    ) AS "infrastructure_usage_cost",
    sum(infrastructure_project_raw_cost) AS "infrastructure_project_raw_cost",
    sum(infrastructure_project_markup_cost) AS "infrastructure_project_markup_cost",
    json_build_object(
        'cpu', sum(((COALESCE(supplementary_project_monthly_cost, '{"cpu": 0}'::jsonb) ->> 'cpu'::text))::numeric),
        'memory', sum(((COALESCE(supplementary_project_monthly_cost, '{"memory": 0}'::jsonb) ->> 'memory'::text))::numeric),
        'pvc', sum(((COALESCE(supplementary_project_monthly_cost, '{"pvc": 0}'::jsonb) ->> 'pvc'::text))::numeric)
    ) AS "supplementary_project_monthly_cost",
    sum(supplementary_monthly_cost) AS "supplementary_monthly_cost",
    json_build_object(
        'cpu', sum(((COALESCE(infrastructure_project_monthly_cost, '{"cpu": 0}'::jsonb) ->> 'cpu'::text))::numeric),
        'memory', sum(((COALESCE(infrastructure_project_monthly_cost, '{"memory": 0}'::jsonb) ->> 'memory'::text))::numeric),
        'pvc', sum(((COALESCE(infrastructure_project_monthly_cost, '{"pvc": 0}'::jsonb) ->> 'pvc'::text))::numeric)
    ) AS "infrastructure_project_monthly_cost",
    sum(infrastructure_monthly_cost) AS "infrastructure_monthly_cost",
    source_uuid
   FROM reporting_ocpusagelineitem_daily_summary
  WHERE (usage_start >= ("date_trunc"('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY usage_start, cluster_id, cluster_alias, namespace, source_uuid

WITH DATA
;

CREATE UNIQUE INDEX ocp_cost_summary_by_project
ON reporting_ocp_cost_summary_by_project (usage_start, cluster_id, cluster_alias, namespace, source_uuid)
;
