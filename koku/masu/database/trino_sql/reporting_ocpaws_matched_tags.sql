WITH cte_enabled_tag_keys AS (
    SELECT array_agg(aws.key) as key_array
    FROM postgres.{{schema_name | sqlsafe}}.reporting_awsenabledtagkeys AS aws
    JOIN postgres.{{schema_name | sqlsafe}}.reporting_ocpenabledtagkeys AS ocp
        ON lower(aws.key) = lower(ocp.key)
    WHERE aws.enabled = true
        AND ocp.enabled = true
),
cte_unnested_aws_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema_name | sqlsafe}}.aws_line_items_daily AS aws
    CROSS JOIN UNNEST(cast(json_parse(resourcetags) as map(varchar, varchar))) AS tags(key, value)
    JOIN cte_enabled_tag_keys AS etk
        ON any_match(etk.key_array, x->strpos(aws.resourcetags, x) != 0)
    WHERE source = {{aws_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND lineitem_usagestartdate >= {{start_date}}
        AND lineitem_usagestartdate < date_add('day', 1, {{end_date}})
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT pod_key,
        pod_value,
        volume_key,
        volume_value
    FROM hive.{{schema_name | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS ocp
    CROSS JOIN UNNEST(
        cast(json_parse(pod_labels) as map(varchar, varchar)),
        cast(json_parse(volume_labels) as map(varchar, varchar))
    ) AS pod_tags(pod_key, pod_value, volume_key, volume_value)
    JOIN cte_enabled_tag_keys AS etk
        ON any_match(etk.key_array, x->strpos(ocp.pod_labels, x) != 0)
            OR any_match(etk.key_array, x->strpos(ocp.volume_labels, x) != 0)
    WHERE source IN {{ocp_source_uuids | inclause}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}}
        AND day IN {{days | inclause}}
)
SELECT '{"' || key || '": "' || value || '"}' as tag
FROM (
    SELECT DISTINCT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_tags AS ocp
        ON (
            lower(aws.key) = lower(ocp.pod_key)
                AND lower(aws.value) = lower(ocp.pod_value)
        )
        OR (
            lower(aws.key) = lower(ocp.volume_key)
                AND lower(aws.value) = lower(ocp.volume_value)
        )
) AS matches
