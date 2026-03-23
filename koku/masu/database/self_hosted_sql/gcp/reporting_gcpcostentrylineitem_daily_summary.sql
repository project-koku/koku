INSERT INTO {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary (
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
    source_uuid,
    invoice_month,
    credit_amount
)
with cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type = 'GCP'
)
SELECT uuid_generate_v4() as uuid,
    INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
    billing_account_id as account_id,
    project_id,
    max(project_name) as project_name,
    service_id,
    max(service_description) as service_alias,
    sku_id,
    max(sku_description) as sku_alias,
    date(usage_start_time) as usage_start,
    date(usage_start_time) as usage_end,
    nullif(location_region, '') as region,
    system_labels::jsonb->>'compute.googleapis.com/machine_spec' as instance_type,
    max(usage_pricing_unit) as unit,
    cast(sum(usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    (SELECT json_object_agg(key, value) FROM jsonb_each_text(labels::jsonb) WHERE key = ANY(pek.keys))::jsonb as tags,
    max(currency) as currency,
    cost_type as line_item_type,
    cast(sum(cost) AS decimal(24,9)) as unblended_cost,
    cast(sum(cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
    '{{source_uuid | sqlsafe}}'::uuid as source_uuid,
    invoice_month,
    sum(((cast(COALESCE((credits::jsonb->>'amount'), '0')AS decimal(24,9)))*1000000)/1000000) as credit_amount
FROM {{schema | sqlsafe}}.{{table | sqlsafe}}
CROSS JOIN
    cte_pg_enabled_keys as pek
WHERE source = '{{source_uuid | sqlsafe}}'
    AND (
        (year = EXTRACT(YEAR FROM DATE({{start_date}}))::text AND month = lpad(EXTRACT(MONTH FROM DATE({{start_date}}))::text, 2, '0'))
        OR
        (year = EXTRACT(YEAR FROM DATE({{end_date}}))::text AND month = lpad(EXTRACT(MONTH FROM DATE({{end_date}}))::text, 2, '0'))
        OR
        (year = EXTRACT(YEAR FROM DATE({{start_date}}) - INTERVAL '1 MONTH')::text AND month = lpad(EXTRACT(MONTH FROM DATE({{start_date}}) - INTERVAL '1 MONTH')::text, 2, '0'))
    )
    AND invoice_month = '{{invoice_month | sqlsafe}}'
    AND usage_start_time >= '{{start_date | sqlsafe}}'::timestamp
    AND usage_start_time < '{{end_date | sqlsafe}}'::timestamp + INTERVAL '1 day'
GROUP BY billing_account_id,
    project_id,
    service_id,
    sku_id,
    date(usage_start_time),
    date(usage_end_time),
    location_region,
    system_labels::jsonb->>'compute.googleapis.com/machine_spec',
    16, -- matches column num of tag's map_filter
    cost_type,
    invoice_month
RETURNING 1;
