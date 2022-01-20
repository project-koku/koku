-- Clear out old entries first
DELETE FROM postgres.{{schema_name | sqlsafe}}.reporting_ocpgcp_cost_summary_by_service_p
WHERE usage_start >= date('{{start_date | sqlsafe}}')
    AND usage_start <= date('{{end_date | sqlsafe}}')
    AND invoice_month = '{{year | sqlsafe}}{{month | sqlsafe}}'
    AND cluster_id = '{{cluster_id | sqlsafe}}'
    AND source_uuid = cast('{{source_uuid | sqlsafe}}' AS UUID)
;

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
    SELECT uuid(),
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
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM postgres.{{schema_name | sqlsafe}}.reporting_ocpgcpcostlineitem_daily_summary_p
    WHERE usage_start >= date('{{start_date | sqlsafe}}')
        AND usage_start <= date('{{end_date | sqlsafe}}')
        AND invoice_month = '{{year | sqlsafe}}{{month | sqlsafe}}'
        AND cluster_id = '{{cluster_id | sqlsafe}}'
        AND source_uuid = cast('{{source_uuid | sqlsafe}}' AS UUID)
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
