-- This file allows us to mimic our trino logic to
-- populate the postgresql summary tables for unit testing.

INSERT INTO {{schema | sqlsafe}}.reporting_ocpgcp_network_summary_p (
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
    SELECT uuid_generate_v4() as id,
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
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM {{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p
    -- Get data for this month or last month
    WHERE (service_alias LIKE '%%Network%%'
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
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND invoice_month = {{invoice_month}}
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        account_id,
        service_id,
        service_alias,
        source_uuid,
        invoice_month
;
