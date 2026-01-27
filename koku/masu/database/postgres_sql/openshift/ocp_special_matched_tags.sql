WITH cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < {{end_date}} + INTERVAL '1 day'
),
cte_cluster_info as (
    select
        '"openshift_cluster": "' || (auth.credentials->>'cluster_id') || '"' AS cluster_id,
        '"openshift_cluster": "' || provider.name || '"' as cluster_alias
    from public.api_provider as provider
    inner join public.api_providerauthentication as auth
    ON provider.authentication_id = auth.id
    and provider.uuid = {{ocp_provider_uuid}}::uuid
),
cte_tag_matches AS (
    SELECT * FROM unnest(CAST(ARRAY{{matched_tag_strs | sqlsafe}} AS VARCHAR[])) as t(matched_tag)

    UNION

    SELECT cluster_alias from cte_cluster_info

    UNION

    SELECT cluster_id from cte_cluster_info

    UNION

    SELECT '"openshift_node": "' || node || '"' AS matched_tag  from cte_array_agg_nodes

    UNION

    SELECT distinct '"openshift_project": "' || namespace || '"'
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
    AND month = {{month}}
    AND year = {{year}}
    AND interval_start >= {{start_date}}
    AND interval_start < {{end_date}} + INTERVAL '1 day'
)
SELECT array_agg(matched_tag) as matched_tags from cte_tag_matches;
