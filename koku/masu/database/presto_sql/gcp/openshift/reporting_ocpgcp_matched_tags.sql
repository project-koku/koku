WITH cte_unnested_gcp_tags AS (
    SELECT DISTINCT key,
        value
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    CROSS JOIN UNNEST(cast(json_parse(labels) as map(varchar, varchar))) AS tags(key, value)
    WHERE source = '{{gcp_source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND usage_start_time >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND usage_start_time < date_add('day', 1, TIMESTAMP '{{start_date | sqlsafe}}')
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
    SELECT DISTINCT gcp.key,
        gcp.value
    FROM cte_unnested_gcp_tags AS gcp
    JOIN cte_unnested_ocp_tags AS ocp
        ON (
            lower(gcp.key) = lower(ocp.pod_key)
                AND lower(gcp.value) = lower(ocp.pod_value)
        )
        OR (
            lower(gcp.key) = lower(ocp.volume_key)
                AND lower(gcp.value) = lower(ocp.volume_value)
        )
    JOIN postgres.{{schema | sqlsafe}}.reporting_gcpenabledtagkeys AS gtk
        ON gcp.key = gtk.key
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys AS otk
        ON ocp.pod_key = otk.key or ocp.volume_key = otk.key
) AS matches
