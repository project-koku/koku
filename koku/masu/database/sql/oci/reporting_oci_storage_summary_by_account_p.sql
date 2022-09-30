DELETE FROM {{schema | sqlsafe}}.reporting_oci_storage_summary_by_account_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_oci_storage_summary_by_account_p (
    id,
    usage_start,
    usage_end,
    usage_amount,
    product_service,
    unit,
    payer_tenant_id,
    cost,
    markup_cost,
    currency,
    source_uuid
)
SELECT uuid_generate_v4() as id,
    usage_start,
    usage_start as usage_end,
    sum(usage_amount) as usage_amount,
    product_service,
    max(unit) as unit,
    payer_tenant_id,
    sum(cost) as cost,
    sum(markup_cost) as markup_cost,
    max(currency) as currency,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary
-- Get data for this month or last month
WHERE product_service LIKE '%%STORAGE%%'
    AND unit in ('GB_MS', 'BYTES_MS', 'BYTES')
    AND usage_start >= {{start_date}}::date
    AND usage_end <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}::uuid
GROUP BY usage_start, payer_tenant_id, product_service
;
