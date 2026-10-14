WITH cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}}
        AND day IN {{days | inclause}}
        AND node IS NOT NULL
        AND node != ''
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
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}}
        AND day IN {{days | inclause}}
        AND namespace IS NOT NULL
        AND namespace != ''
)
SELECT array_agg(matched_tag) as matched_tags from cte_tag_matches;
