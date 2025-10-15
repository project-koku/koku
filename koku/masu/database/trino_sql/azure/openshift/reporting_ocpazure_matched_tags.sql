

WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    CROSS JOIN UNNEST(cast(json_parse(tags) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = {{azure_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND date >= {{start_date}}
        AND date < date_add('day', 1, {{end_date}})
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT pod_key,
        pod_value,
        volume_key,
        volume_value
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS ocp
    CROSS JOIN UNNEST(
        cast(json_parse(pod_labels) as map(varchar, varchar)),
        cast(json_parse(volume_labels) as map(varchar, varchar))
    ) AS pod_tags(pod_key, pod_value, volume_key, volume_value)
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
    JOIN postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON azure.key = etk.key
       AND etk.enabled = true
       AND etk.provider_type = 'Azure'
    JOIN postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys AS otk
        ON ocp.pod_key = otk.key or ocp.volume_key = otk.key
        AND otk.provider_type = 'OCP'
) AS matches
