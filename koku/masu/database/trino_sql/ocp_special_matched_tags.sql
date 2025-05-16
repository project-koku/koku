WITH cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_cluster_info as (
    select
        format('"openshift_cluster": "%s"', json_extract_scalar(auth.credentials, '$.cluster_id')) AS cluster_id,
        format('"openshift_cluster": "%s"', provider.name) as cluster_alias
    from postgres.public.api_provider as provider
    inner join postgres.public.api_providerauthentication as auth
    ON provider.authentication_id = auth.id
    and provider.uuid = CAST({{ocp_provider_uuid}} as UUID)
),
cte_tag_matches AS (
    SELECT * FROM unnest(ARRAY{{matched_tag_strs | sqlsafe}}) as t(matched_tag)

    UNION

    SELECT cluster_alias from cte_cluster_info

    UNION

    SELECT cluster_id from cte_cluster_info

    UNION

    SELECT format('"openshift_node": "%s"', node) AS matched_tag  from cte_array_agg_nodes

    UNION

    SELECT distinct format('"openshift_project": "%s"', namespace)
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
    AND month = {{month}}
    AND year = {{year}}
    AND interval_start >= {{start_date}}
    AND interval_start < date_add('day', 1, {{end_date}})
)
SELECT array_agg(matched_tag) as matched_tags from cte_tag_matches;
