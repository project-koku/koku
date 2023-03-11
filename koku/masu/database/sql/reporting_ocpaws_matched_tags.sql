WITH
    cte_aws_tag_keys AS (
        SELECT DISTINCT ts.key
        FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts
    JOIN {{schema | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    ),

    cte_ocp_tag_keys AS (
        SELECT DISTINCT ts.key
        FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
    ),

    cte_matched_tag_keys AS (
        SELECT DISTINCT
            cte_aws_tag_keys.key AS aws_key,
            cte_ocp_tag_keys.key AS ocp_key
        FROM cte_aws_tag_keys
        INNER JOIN cte_ocp_tag_keys
        ON lower(cte_aws_tag_keys.key) = lower(cte_ocp_tag_keys.key)
    ),

    cte_unnested_aws_tags AS (
        SELECT DISTINCT
            ts.key,
            ts.value
        FROM {{schema | sqlsafe}}.reporting_awstags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_awsenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
        WHERE ts.key IN (SELECT aws_key FROM cte_matched_tag_keys)
    ),

    cte_unnested_ocp_tags AS (
        SELECT DISTINCT
            ts.key,
            ts.value
        FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ts
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(ts.key)
        WHERE ts.key IN (SELECT ocp_key FROM cte_matched_tag_keys)
    )

SELECT jsonb_build_object(key, value) AS tag
FROM (
    SELECT
        cte_unnested_aws_tags.key,
        cte_unnested_aws_tags.value
    FROM cte_unnested_aws_tags
    INNER JOIN cte_unnested_ocp_tags
    ON
        lower(cte_unnested_aws_tags.key) = lower(cte_unnested_ocp_tags.key)
        AND lower(cte_unnested_aws_tags.value) = lower(cte_unnested_ocp_tags.value)
) AS matches
;
