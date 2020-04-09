INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (
    key,
    values,
    cost_entry_bill_id,
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
        FROM reporting_awstags_summary AS ts,
            unnest(ts.values) AS values(value)
    ) AS tags
    JOIN reporting_awscostentrybill AS b
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
        FROM reporting_ocpusagepodlabel_summary AS ts,
            unnest(ts.values) AS values(value),
            unnest(ts.namespace) AS namespaces(project)
    ) AS tags
    JOIN reporting_ocpusagereportperiod AS rp
        ON tags.report_period_id = rp.id
),
cte_unnested_ocp_volume_tags AS (
    SELECT tags.*,
        rp.report_period_start
    FROM (
        SELECT key,
            value,
            report_period_id,
            project
        FROM reporting_ocpstoragevolumelabel_summary AS ts,
            unnest(ts.values) AS values(value),
            unnest(ts.namespace) AS namespaces(project)
    ) AS tags
    JOIN reporting_ocpusagereportperiod AS rp
        ON tags.report_period_id = rp.id
)
SELECT key,
    array_agg(DISTINCT value) as values,
    cost_entry_bill_id,
    accounts,
    array_agg(DISTINCT project) as namespace
FROM (
    SELECT aws.key,
        aws.value,
        aws.accounts,
        ocp.project,
        aws.cost_entry_bill_id
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_pod_tags AS ocp
        ON aws.key = ocp.key
            AND aws.value = ocp.value
            AND aws.billing_period_start = ocp.report_period_start

    UNION

    SELECT aws.key,
        aws.value,
        aws.accounts,
        ocp.project,
        aws.cost_entry_bill_id
    FROM cte_unnested_aws_tags AS aws
    JOIN cte_unnested_ocp_volume_tags AS ocp
        ON aws.key = ocp.key
            AND aws.value = ocp.value
            AND aws.billing_period_start = ocp.report_period_start
) AS matches
GROUP BY key,
    accounts,
    cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
