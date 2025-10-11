DELETE FROM {{schema | sqlsafe}}.reporting_gcp_network_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND invoice_month = {{invoice_month}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_gcp_network_summary_p (
    id,
    usage_start,
    usage_end,
    account_id,
    usage_amount,
    unit,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    service_id,
    service_alias,
    invoice_month,
    credit_amount
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        account_id,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid,
        service_id,
        service_alias,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary
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
        AND source_uuid = {{source_uuid}}
        AND invoice_month = {{invoice_month}}
    GROUP BY usage_start, account_id, service_id, service_alias, invoice_month
;
