-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema_name | sqlsafe}}.reporting_ocpgcp_cost_summary_by_service_p (
    id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    account_id,
    service_id,
    service_alias,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid() as id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        account_id,
        service_id,
        service_alias,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        cast({{gcp_source_uuid}} as uuid) as source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM hive.{{schema_name | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary
    WHERE gcp_source = {{gcp_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND invoice_month = {{invoice_month}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
    GROUP BY cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        account_id,
        service_id,
        service_alias,
        invoice_month
