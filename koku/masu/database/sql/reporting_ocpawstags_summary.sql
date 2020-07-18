INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (
    key,
    values,
    cost_entry_bill_id,
    report_period_id,
    accounts,
    namespace
)
WITH cte_unnested_aws_tags AS (
    SELECT tags.*,
        b.billing_period_start
    FROM (
        SELECT key,
            value,
            cost_entry_bill_id,
            accounts
        FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts,
            unnest(ts.values) AS values(value)
    ) AS tags
    JOIN {{schema | sqlsafe}}.reporting_awscostentrybill AS b
        ON tags.cost_entry_bill_id = b.id
),
cte_unnested_ocp_pod_tags AS (
    SELECT tags.*,
        rp.report_period_start
    FROM (
        SELECT key,
            value,
            report_period_id,
            project
        FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ts,
            unnest(ts.values) AS values(value),
            unnest(ts.namespace) AS namespaces(project)
    ) AS tags
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON tags.report_period_id = rp.id
    -- Filter out tags that aren't enabled
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(tags.key)
),
cte_unnested_ocp_volume_tags AS (
    SELECT tags.*,
        rp.report_period_start
    FROM (
        SELECT key,
            value,
            report_period_id,
            project
        FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ts,
            unnest(ts.values) AS values(value),
            unnest(ts.namespace) AS namespaces(project)
    ) AS tags
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON tags.report_period_id = rp.id
    -- Filter out tags that aren't enabled
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys as enabled_tags
        ON lower(enabled_tags.key) = lower(tags.key)
)
SELECT key,
    array_agg(DISTINCT value) as values,
    cost_entry_bill_id,
    report_period_id,
    accounts,
    array_agg(DISTINCT project) as namespace
FROM (
    SELECT aws.key,
        aws.value,
        aws.accounts,
        ocp.project,
        aws.cost_entry_bill_id,
        ocp.report_period_id
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_pod_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)
            AND aws.billing_period_start = ocp.report_period_start

    UNION

    SELECT aws.key,
        aws.value,
        aws.accounts,
        ocp.project,
        aws.cost_entry_bill_id,
        ocp.report_period_id
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_volume_tags AS ocp
        ON lower(aws.key) = lower(ocp.key)
            AND lower(aws.value) = lower(ocp.value)
            AND aws.billing_period_start = ocp.report_period_start
) AS matches
GROUP BY key,
    accounts,
    cost_entry_bill_id,
    report_period_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
