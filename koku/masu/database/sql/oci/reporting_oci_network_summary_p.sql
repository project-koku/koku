DELETE FROM {{schema | sqlsafe}}.reporting_oci_network_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;
INSERT INTO {{schema | sqlsafe}}.reporting_oci_network_summary_p (
    id,
    usage_start,
    usage_end,
    payer_tenant_id,
    product_service,
    usage_amount,
    unit,
    cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        payer_tenant_id,
        product_service,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(cost) as cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{source_uuid}}::uuid as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND product_service IN ('NETWORK')
    GROUP BY usage_start, payer_tenant_id, product_service
;
