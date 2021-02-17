
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary (
    uuid,
    cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    usage_start,
    usage_end,
    region,
    instance_type,
    unit,
    usage_amount,
    tags,
    currency,
    line_item_type,
    unblended_cost,
    markup_cost,
    source_uuid
)
SELECT uuid() as uuid,
    INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
    billing_account_id as account_id,
    project_id,
    max(project_name) as project_name,
    service_id,
    max(service_description) as service_alias,
    sku_id,
    max(sku_description) as sku_alias,
    date(usage_start_time) as usage_start,
    date(usage_end_time) as usage_end,
    nullif(location_region, '') as region,
    json_extract_scalar(json_parse(system_labels), '$["compute.googleapis.com/machine_spec"]') as instance_type,
    max(usage_pricing_unit) as unit,
    cast(sum(usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    json_parse(labels) as tags,
    max(currency) as currency,
    cost_type as line_item_type,
    cast(sum(cost) AS decimal(24,9)) as unblended_cost,
    cast(sum(cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE source = '{{source_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND date(usage_start_time) >= date('{{start_date | sqlsafe}}')
    AND date(usage_start_time) <= date('{{end_date | sqlsafe}}')
GROUP BY billing_account_id,
    project_id,
    service_id,
    sku_id,
    date(usage_start_time),
    date(usage_end_time),
    location_region,
    json_extract_scalar(json_parse(system_labels), '$["compute.googleapis.com/machine_spec"]'),
    labels,
    cost_type
