WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema_name | sqlsafe}}.reporting_azuretags_values AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_azureenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
       AND enabled_tags.enabled = true
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema_name | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
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
