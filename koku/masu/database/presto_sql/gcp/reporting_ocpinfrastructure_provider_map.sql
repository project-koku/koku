{% if not resource_level%}
    WITH cte_openshift_cluster_info AS (
    SELECT DISTINCT cluster_id,
        cluster_alias,
        cast(provider_id as varchar) as provider_id
    FROM postgres.{{schema | sqlsafe}}.reporting_ocp_clusters
    ),
    cte_distinct_gcp_labels AS (
    SELECT DISTINCT labels,
        source
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily
    WHERE source = '{{gcp_provider_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
    ),
    cte_label_keys AS (
    SELECT cast(json_parse(labels) as map(varchar, varchar)) as parsed_labels,
        source
    FROM cte_distinct_gcp_labels
    )
    SELECT ocp.provider_id as ocp_uuid,
        gcp.source as infra_uuid,
        'GCP' as type
    FROM cte_label_keys as gcp
    INNER JOIN cte_openshift_cluster_info as ocp
        ON any_match(map_keys(gcp.parsed_labels), e -> e = 'kubernetes-io-cluster-' || ocp.cluster_id)
            OR any_match(map_keys(gcp.parsed_labels), e -> e = 'kubernetes-io-cluster-' || ocp.cluster_alias)
            OR element_at(gcp.parsed_labels, 'openshift_cluster')  IN (ocp.cluster_id, ocp.cluster_alias)
{% endif %}

{% if resource_level %}
    WITH cte_gcp_resource_name AS (
        SELECT DISTINCT gcp.resource_name,
            gcp.source
        FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
        WHERE gcp.usage_start_time >= TIMESTAMP '{{start_date | sqlsafe}}'
            AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
            {% if gcp_provider_uuid %}
            AND gcp.source = '{{gcp_provider_uuid | sqlsafe}}'
            {% endif %}
            AND gcp.year = '{{year | sqlsafe}}'
            AND gcp.month = '{{month | sqlsafe}}'
    ),
    cte_ocp_nodes AS (
        SELECT DISTINCT ocp.node,
            ocp.source
        FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        WHERE ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
            AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
            AND ocp.node IS NOT NULL
            AND ocp.node != ''
            {% if ocp_provider_uuid %}
            AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
            {% endif %}
            AND ocp.year = '{{year | sqlsafe}}'
            AND ocp.month = '{{month | sqlsafe}}'
    )
    SELECT DISTINCT ocp.source as ocp_uuid,
        gcp.source as infra_uuid,
        'GCP' as type
    FROM cte_gcp_resource_name AS gcp
    JOIN cte_ocp_nodes AS ocp
        ON strpos(gcp.resource_name, ocp.node) != 0
;
