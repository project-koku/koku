

WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    CROSS JOIN UNNEST(cast(json_parse(tags) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{azure_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND coalesce(usagedatetime, date) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND coalesce(usagedatetime, date) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
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
    WHERE source IN ('{{ocp_source_uuids | sqlsafe}}')
        AND year = '{{year | sqlsafe}}'
        AND lpad(month, 2, '0') = '{{month | sqlsafe}}'
        AND day IN ('{{days | sqlsafe}}')
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
    JOIN postgres.{{schema | sqlsafe}}.reporting_azureenabledtagkeys AS atk
        ON azure.key = atk.key
       AND atk.enabled = true
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys AS otk
        ON ocp.pod_key = otk.key or ocp.volume_key = otk.key
) AS matches
