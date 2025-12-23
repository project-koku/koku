

WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT key,
        value
    FROM {{schema | sqlsafe}}.azure_line_items AS azure
    CROSS JOIN LATERAL json_each_text(azure.tags::json) AS tags(key, value)
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
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_trino AS ocp
    CROSS JOIN LATERAL json_each_text(COALESCE(ocp.pod_labels::json, '{}'::json)) AS pod_tags(pod_key, pod_value)
    CROSS JOIN LATERAL json_each_text(COALESCE(ocp.volume_labels::json, '{}'::json)) AS volume_tags(volume_key, volume_value)
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
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON azure.key = etk.key
       AND etk.enabled = true
       AND etk.provider_type = 'Azure'
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS otk
        ON ocp.pod_key = otk.key or ocp.volume_key = otk.key
        AND otk.provider_type = 'OCP'
) AS matches
