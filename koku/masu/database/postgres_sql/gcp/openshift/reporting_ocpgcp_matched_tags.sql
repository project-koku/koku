WITH cte_unnested_gcp_tags AS (
    SELECT DISTINCT key,
        value
    FROM {{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    CROSS JOIN LATERAL jsonb_each_text(gcp.labels::jsonb) AS tags(key, value)
    WHERE source = {{gcp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < {{start_date}} + INTERVAL '1 day'
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT pod_key,
        pod_value,
        volume_key,
        volume_value
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_trino AS ocp
    CROSS JOIN LATERAL jsonb_each_text(COALESCE(ocp.pod_labels::jsonb, '{}'::jsonb)) AS pod_tags(pod_key, pod_value)
    CROSS JOIN LATERAL jsonb_each_text(COALESCE(ocp.volume_labels::jsonb, '{}'::jsonb)) AS volume_tags(volume_key, volume_value)
    WHERE source IN {{ocp_source_uuids | inclause}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}}
        AND day IN {{days | inclause}}
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
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON gcp.key = etk.key
        AND etk.enabled = true
        AND etk.provider_type = 'GCP'
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS otk
        ON ocp.pod_key = otk.key or ocp.volume_key = otk.key
        AND otk.provider_type = 'OCP'

) AS matches
