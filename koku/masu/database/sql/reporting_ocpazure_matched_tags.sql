WITH cte_unnested_azure_tags AS (
    SELECT DISTINCT
ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_azuretags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_azureenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
       AND enabled_tags.enabled = true
),

cte_unnested_ocp_tags AS (
    SELECT DISTINCT
ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
)

SELECT jsonb_build_object(key, value) AS tag
FROM (
    SELECT
cte_unnested_azure_tags.key,
        cte_unnested_azure_tags.value
    FROM cte_unnested_azure_tags
    INNER JOIN cte_unnested_ocp_tags
        ON lower(cte_unnested_azure_tags.key) = lower(cte_unnested_ocp_tags.key)
            AND lower(cte_unnested_azure_tags.value) = lower(cte_unnested_ocp_tags.value)
) AS matches
;
