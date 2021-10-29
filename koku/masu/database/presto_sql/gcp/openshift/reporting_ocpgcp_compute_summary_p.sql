-- Clear out old entries first
DELETE FROM postgres.{{schema | sqlsafe}}.reporting_ocpgcp_compute_summary_p
WHERE usage_start >= date('{{start_date | sqlsafe}}')
    AND usage_start <= date('{{end_date | sqlsafe}}')
    AND invoice_month = '{{year | sqlsafe}}{{month | sqlsafe}}'
;

-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcp_compute_summary_p (
    id,
    account_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    instance_type,
    unblended_cost,
    markup_cost,
    currency,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid(),
        account_id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        instance_type,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_daily_summary_p
    WHERE usage_start >= date('{{start_date | sqlsafe}}')
        AND usage_start <= date('{{end_date | sqlsafe}}')
        AND invoice_month = '{{year | sqlsafe}}{{month | sqlsafe}}'
    GROUP BY cluster_id,
        account_id,
        cluster_alias,
        usage_start,
        usage_end,
        source_uuid,
        instance_type,
        invoice_month
;
