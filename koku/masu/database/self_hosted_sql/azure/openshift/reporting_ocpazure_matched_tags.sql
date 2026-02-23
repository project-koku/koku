
WITH cte_enabled_tag_keys AS (
    SELECT array_agg(key) as key_array
    FROM (
        SELECT key,
            count(provider_type) AS p_count
        FROM {{schema | sqlsafe}}.reporting_enabledtagkeys
        WHERE enabled = true
            AND provider_type IN ('Azure', 'OCP')
            GROUP BY key
    ) c
    WHERE c.p_count > 1
),
cte_unnested_azure_tags AS (
    SELECT DISTINCT key,
        value
    FROM {{schema | sqlsafe}}.azure_line_items AS azure
    CROSS JOIN LATERAL jsonb_each_text(azure.tags::jsonb) AS tags(key, value)
    JOIN cte_enabled_tag_keys AS etk
        ON EXISTS (
            SELECT 1
            FROM unnest(etk.key_array) AS enabled_key
            WHERE strpos(azure.tags, enabled_key) != 0
        )
    WHERE source = {{azure_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND date >= {{start_date}}
        AND date < {{end_date}} + INTERVAL '1 day'
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT pod_key,
        pod_value,
        volume_key,
        volume_value
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging AS ocp
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
    SELECT DISTINCT azure.key,
        azure.value
    FROM cte_unnested_azure_tags AS azure
    JOIN cte_unnested_ocp_tags AS ocp
        ON (
            lower(azure.key) = lower(ocp.pod_key)
                AND lower(azure.value) = lower(ocp.pod_value)
        )
        OR (
            lower(azure.key) = lower(ocp.volume_key)
                AND lower(azure.value) = lower(ocp.volume_value)
        )
) AS matches
