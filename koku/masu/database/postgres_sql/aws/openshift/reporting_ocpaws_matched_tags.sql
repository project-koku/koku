WITH cte_enabled_tag_keys AS (
    SELECT array_agg(key) as key_array
    FROM (
        SELECT key,
            count(provider_type) AS p_count
        FROM {{schema | sqlsafe}}.reporting_enabledtagkeys
        WHERE enabled = true
            AND provider_type IN ('AWS', 'OCP')
            GROUP BY key
    ) c
    WHERE c.p_count > 1
),
cte_unnested_aws_tags AS (
    SELECT DISTINCT key,
        value
    FROM {{schema | sqlsafe}}.aws_line_items_daily AS aws
    CROSS JOIN LATERAL jsonb_each_text(aws.resourcetags::jsonb) AS tags(key, value)
    JOIN cte_enabled_tag_keys AS etk
        ON EXISTS (
            SELECT 1
            FROM unnest(etk.key_array) AS enabled_key
            WHERE strpos(aws.resourcetags, enabled_key) != 0
        )
    WHERE source = {{aws_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND lineitem_usagestartdate >= {{start_date}}
        AND lineitem_usagestartdate < {{end_date}} + INTERVAL '1 day'
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT pod_key,
        pod_value,
        volume_key,
        volume_value
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_trino AS ocp
    CROSS JOIN LATERAL jsonb_each_text(COALESCE(ocp.pod_labels::jsonb, '{}'::jsonb)) AS pod_tags(pod_key, pod_value)
    CROSS JOIN LATERAL jsonb_each_text(COALESCE(ocp.volume_labels::jsonb, '{}'::jsonb)) AS volume_tags(volume_key, volume_value)
    JOIN cte_enabled_tag_keys AS etk
        ON EXISTS (
            SELECT 1
            FROM unnest(etk.key_array) AS enabled_key
            WHERE strpos(ocp.pod_labels, enabled_key) != 0
                OR strpos(ocp.volume_labels, enabled_key) != 0
        )
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
