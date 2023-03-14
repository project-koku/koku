WITH
    cte_unnested_gcp_tags AS (
        SELECT DISTINCT
            key,
            value
        FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    CROSS JOIN UNNEST(cast(json_parse(labels) as map(varchar, varchar))) AS tags(key, value)
        WHERE source = {{gcp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < date_add('day', 1, {{start_date}})
    ),

    cte_unnested_ocp_tags AS (
        SELECT DISTINCT
            pod_key,
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

SELECT '{"' || key || '": "' || value || '"}' AS tag
FROM (
    SELECT DISTINCT
        cte_unnested_gcp_tags.key,
        cte_unnested_gcp_tags.value
    FROM cte_unnested_gcp_tags
    INNER JOIN cte_unnested_ocp_tags
    ON (
        lower(cte_unnested_gcp_tags.key) = lower(cte_unnested_ocp_tags.pod_key)
        AND lower(cte_unnested_gcp_tags.value) = lower(cte_unnested_ocp_tags.pod_value)
    )
    OR (
        lower(cte_unnested_gcp_tags.key) = lower(cte_unnested_ocp_tags.volume_key)
        AND lower(cte_unnested_gcp_tags.value) = lower(cte_unnested_ocp_tags.volume_value)
    )
    INNER JOIN postgres.{{schema | sqlsafe}}.reporting_gcpenabledtagkeys AS gtk
        ON cte_unnested_gcp_tags.key = gtk.key
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys AS otk
        ON cte_unnested_ocp_tags.pod_key = otk.key or cte_unnested_ocp_tags.volume_key = otk.key
) AS matches
;
