INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (
    key,
    values,
    cost_entry_bill_id,
    report_period_id,
    subscription_guid,
    namespace,
    cluster_id,
    cluster_alias
)
WITH cte_unnested_azure_tags AS (
    SELECT tags.*,
        b.billing_period_start
    FROM (
        SELECT key,
            value,
            cost_entry_bill_id,
            accounts
        FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts,
            unnest(ts.values) AS values(value)
    ) AS tags
    JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill AS b
        ON tags.cost_entry_bill_id = b.id
),
cte_unnested_ocp_pod_tags AS (
    SELECT tags.*,
        rp.report_period_start,
        rp.cluster_id,
        rp.cluster_alias
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
        rp.report_period_start,
        rp.cluster_id,
        rp.cluster_alias
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
    array_agg(DISTINCT project) as namespace,
    max(cluster_id) as cluster_id,
    max(cluster_alias) as cluster_alias
FROM (
    SELECT azure.key,
        azure.value,
        azure.accounts,
        ocp.project,
        azure.cost_entry_bill_id,
        ocp.report_period_id,
        ocp.cluster_id,
        ocp.cluster_alias
    FROM cte_unnested_azure_tags AS azure
    JOIN cte_unnested_ocp_pod_tags AS ocp
        ON lower(azure.key) = lower(ocp.key)
            AND lower(azure.value) = lower(ocp.value)
            AND azure.billing_period_start = ocp.report_period_start

    UNION

    SELECT azure.key,
        azure.value,
        azure.accounts,
        ocp.project,
        azure.cost_entry_bill_id,
        ocp.report_period_id,
        ocp.cluster_id,
        ocp.cluster_alias
    FROM cte_unnested_azure_tags AS azure
    JOIN cte_unnested_ocp_volume_tags AS ocp
        ON lower(azure.key) = lower(ocp.key)
            AND lower(azure.value) = lower(ocp.value)
            AND azure.billing_period_start = ocp.report_period_start
) AS matches
GROUP BY key,
    accounts,
    cost_entry_bill_id,
    report_period_id
ON CONFLICT (key, cost_entry_bill_id, namespace) DO UPDATE
SET values = EXCLUDED.values
;
