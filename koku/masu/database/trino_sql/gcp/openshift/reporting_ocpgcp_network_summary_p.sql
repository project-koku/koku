-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema_name | sqlsafe}}.reporting_ocpgcp_network_summary_p (
    id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    usage_amount,
    unit,
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
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
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
    -- Get data for this month or last month
    WHERE gcp_source = {{gcp_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND invoice_month = {{invoice_month}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
        AND (service_alias LIKE '%%Network%%'
        OR service_alias LIKE '%%VPC%%'
        OR service_alias LIKE '%%Firewall%%'
        OR service_alias LIKE '%%Route%%'
        OR service_alias LIKE '%%IP%%'
        OR service_alias LIKE '%%DNS%%'
        OR service_alias LIKE '%%CDN%%'
        OR service_alias LIKE '%%NAT%%'
        OR service_alias LIKE '%%Traffic Director%%'
        OR service_alias LIKE '%%Service Discovery%%'
        OR service_alias LIKE '%%Cloud Domains%%'
        OR service_alias LIKE '%%Private Service Connect%%'
        OR service_alias LIKE '%%Cloud Armor%%')
    GROUP BY cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        account_id,
        service_id,
        service_alias,
        invoice_month
