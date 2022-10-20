DELETE FROM {{schema | sqlsafe}}.reporting_oci_storage_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_oci_storage_summary_p (
    id,
    usage_start,
    usage_end,
    usage_amount,
    product_service,
    unit,
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
    sum(cost) as cost,
    sum(markup_cost) as markup_cost,
    max(currency) as currency,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary
-- Get data for this month or last month
WHERE product_service LIKE '%%STORAGE%%'
    AND unit = 'GB-Mo'
    AND usage_start >= {{start_date}}::date
    AND usage_end <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
GROUP BY usage_start, product_service
;
