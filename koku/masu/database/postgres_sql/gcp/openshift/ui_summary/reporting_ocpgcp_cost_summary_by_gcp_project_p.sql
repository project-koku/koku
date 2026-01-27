-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpgcp_cost_summary_by_gcp_project_p (
    id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    project_id,
    project_name,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        project_id,
        project_name,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{gcp_source_uuid}}::uuid as source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM {{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary
    WHERE source = {{gcp_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= {{end_date}} + INTERVAL '1 day'
    GROUP BY cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        project_id,
        project_name,
        invoice_month
RETURNING 1;
