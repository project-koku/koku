-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcp_compute_summary_p (
    id,
    account_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    usage_amount,
    unit,
    instance_type,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid() as id,
        account_id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        instance_type,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        cast({{gcp_source_uuid}} as uuid) as source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary
    WHERE source = {{gcp_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
    GROUP BY cluster_id,
        account_id,
        cluster_alias,
        usage_start,
        usage_end,
        instance_type,
        invoice_month
