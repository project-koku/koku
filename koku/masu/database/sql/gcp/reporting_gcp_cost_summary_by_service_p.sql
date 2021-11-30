DELETE FROM {{schema | sqlsafe}}.reporting_gcp_cost_summary_by_service_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND invoice_month = {{invoice_month}}
;

INSERT INTO reporting_gcp_cost_summary_by_service_p (
    id,
    usage_start,
    usage_end,
    account_id,
    service_id,
    service_alias,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    invoice_month,
    credit_amount
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        account_id,
        service_id,
        service_alias,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(source_uuid::text)::uuid as source_uuid,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND invoice_month = {{invoice_month}}
    GROUP BY usage_start, account_id, service_id, service_alias, invoice_month
;
