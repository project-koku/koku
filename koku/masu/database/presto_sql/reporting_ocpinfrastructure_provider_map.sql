{% if check_gcp and not resource_level%}
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
{% endif %}

{% if check_aws %}
    SELECT DISTINCT ocp.source as ocp_uuid,
        aws.source as infra_uuid,
        'AWS' as type
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        ON aws.lineitem_usagestartdate = ocp.interval_start
            AND aws.lineitem_resourceid IS NOT NULL
            AND aws.lineitem_resourceid != ''
            AND ocp.resource_id IS NOT NULL
            AND ocp.resource_id != ''
            AND ocp.resource_id = aws.lineitem_resourceid
    WHERE aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if aws_provider_uuid %}
        AND aws.source = '{{aws_provider_uuid | sqlsafe}}'
        AND aws.year = '{{year | sqlsafe}}'
        AND aws.month = '{{month | sqlsafe}}'
        {% endif %}
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
        {% endif %}
{% endif %}

{% if ocp_provider_uuid and check_azure and check_aws  %}
    UNION
{% endif %}

{% if check_azure %}
    SELECT DISTINCT ocp.source as ocp_uuid,
        azure.source as infra_uuid,
        'Azure' as type
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        ON coalesce(azure.date, azure.usagedatetime) = ocp.interval_start
            AND ocp.node IS NOT NULL
            AND ocp.node != ''
            AND ocp.node = split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9)
    WHERE coalesce(azure.date, azure.usagedatetime) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if azure_provider_uuid %}
        AND azure.source = '{{azure_provider_uuid | sqlsafe}}'
        AND azure.year = '{{year | sqlsafe}}'
        AND azure.month = '{{month | sqlsafe}}'
        {% endif %}
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
        {% endif %}
{% endif %}

{% if ocp_provider_uuid and check_gcp and (check_aws or check_azure)  %}
    UNION
{% endif %}

{% if check_gcp and not resource_level%}
    SELECT ocp.provider_id as ocp_uuid,
        gcp.source as infra_uuid,
        'GCP' as type
    FROM cte_label_keys as gcp
    INNER JOIN cte_openshift_cluster_info as ocp
        ON any_match(map_keys(gcp.parsed_labels), e -> e = 'kubernetes-io-cluster-' || ocp.cluster_id)
            OR any_match(map_keys(gcp.parsed_labels), e -> e = 'kubernetes-io-cluster-' || ocp.cluster_alias)
            OR element_at(gcp.parsed_labels, 'openshift_cluster')  IN (ocp.cluster_id, ocp.cluster_alias)
{% endif %}

{% if check_gcp and resource_level %}
    SELECT DISTINCT ocp.source as ocp_uuid,
        gcp.source as infra_uuid,
        'GCP' as type
    FROM hive.{{schema | sqlsafe}}.gcp_line_items AS gcp
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        ON gcp.usage_start_time = ocp.interval_start
            AND ocp.node IS NOT NULL
            AND ocp.node != ''
            AND strpos(gcp.resource_name, ocp.node) != 0
    WHERE gcp.usage_start_time >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if gcp_provider_uuid %}
        AND gcp.source = '{{gcp_provider_uuid | sqlsafe}}'
        AND gcp.year = '{{year | sqlsafe}}'
        AND gcp.month = '{{month | sqlsafe}}'
        {% endif %}
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
        {% endif %}
{% endif %}
