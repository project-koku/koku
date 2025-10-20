WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_azuretags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
       AND enabled_tags.enabled = true
       AND enabled_tags.provider_type = 'Azure'
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
    SELECT azure.key,
        azure.value
    FROM cte_unnested_azure_tags AS azure
    JOIN cte_unnested_ocp_tags AS ocp
        ON lower(azure.key) = lower(ocp.key)
            AND lower(azure.value) = lower(ocp.value)
) AS matches
;
