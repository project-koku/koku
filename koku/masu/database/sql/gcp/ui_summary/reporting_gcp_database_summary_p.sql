DELETE FROM {{schema | sqlsafe}}.reporting_gcp_database_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND invoice_month = {{invoice_month}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_gcp_database_summary_p (
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
    WHERE (service_alias LIKE '%%SQL%%'
        OR service_alias LIKE '%%Spanner%%'
        OR service_alias LIKE '%%Bigtable%%'
        OR service_alias LIKE '%%Firestore%%'
        OR service_alias LIKE '%%Firebase%%'
        OR service_alias LIKE '%%Memorystore%%'
        OR service_alias LIKE '%%MongoDB%%')
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND invoice_month = {{invoice_month}}
    GROUP BY usage_start, account_id, service_id, service_alias, invoice_month
;
