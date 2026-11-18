WITH cte_unnested_gcp_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_gcptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    WHERE enabled_tags.provider_type = 'GCP'
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    WHERE enabled_tags.provider_type = 'OCP'
)
SELECT jsonb_build_object(key, value) as tag
FROM (
    SELECT gcp.key,
        gcp.value
    FROM cte_unnested_gcp_tags AS gcp
    JOIN cte_unnested_ocp_tags AS ocp
        ON lower(gcp.key) = lower(ocp.key)
            AND lower(gcp.value) = lower(ocp.value)
) AS matches
;
