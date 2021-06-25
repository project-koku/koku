

WITH cte_unnested_aws_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
    CROSS JOIN UNNEST(cast(json_parse(resourcetags) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{aws_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
),
cte_unnested_ocp_node_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items_daily AS ocp
    CROSS JOIN UNNEST(cast(json_parse(node_labels) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{ocp_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
),
cte_unnested_ocp_namespace_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily AS ocp
    CROSS JOIN UNNEST(cast(json_parse(namespace_labels) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{ocp_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
),
cte_unnested_ocp_pod_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    CROSS JOIN UNNEST(cast(json_parse(pod_labels) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{ocp_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
),
cte_unnested_ocp_volume_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily AS ocp
    CROSS JOIN UNNEST(cast(json_parse(persistentvolumeclaim_labels) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{ocp_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
)
SELECT '{"' || key || '": "' || value || '"}' as tag
FROM (
    SELECT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_pod_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)

    UNION

    SELECT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_node_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)

    UNION

    SELECT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_namespace_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)


    UNION

    SELECT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_volume_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)
) AS matches
