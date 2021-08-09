WITH cte_unnested_aws_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_awstags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
)
SELECT jsonb_build_object(key, value) as tag
FROM (
    SELECT aws.key,
        aws.value
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)
) AS matches
;
