WITH cte_aws_tag_keys AS (
    SELECT DISTINCT ts.key
    FROM {{schema_name | sqlsafe}}.reporting_awstags_summary AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
),
cte_ocp_tag_keys AS (
    SELECT DISTINCT ts.key
    FROM {{schema_name | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
),
cte_matched_tag_keys AS (
    SELECT DISTINCT aws.key as aws_key,
        ocp.key as ocp_key
    FROM cte_aws_tag_keys AS aws
    JOIN cte_ocp_tag_keys AS ocp
        ON lower(aws.key) = lower(ocp.key)
),
cte_unnested_aws_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema_name | sqlsafe}}.reporting_awstags_values AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    WHERE ts.key IN (SELECT aws_key FROM cte_matched_tag_keys)
),
cte_unnested_ocp_tags AS (
    SELECT DISTINCT ts.key,
        ts.value
    FROM {{schema_name | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema_name | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    WHERE ts.key IN (SELECT ocp_key FROM cte_matched_tag_keys)
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
