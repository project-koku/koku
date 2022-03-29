INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary (
    uuid,
    cost_entry_bill_id,
    usage_start,
    usage_end,
    payer_tenant_id,
    product_service,
    region,
    resource_ids,
    resource_count,
    currency_code,
    cost,
    tags,
    source_uuid,
    markup_cost
)
with cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_ocienabledtagkeys
     where enabled = true
)
SELECT uuid() as uuid,
    INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
    usage_start,
    usage_end,
    cast(payer_tenant_id AS varchar(50)),
    cast(product_service AS varchar(50)),
    cast(region AS varchar(50)),
    resource_ids,
    cast(resource_count AS integer),
    cast(currency_code AS varchar(10)),
    cast(cost AS decimal(24,9)),
    tags,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    cast(cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost
FROM (
    SELECT date(lineitem_intervalusagestart) as usage_start,
        date(lineitem_intervalusagestart) as usage_end,
        lineitem_tenantid as payer_tenant_id,
        nullif(product_service, '') as product_service,
        nullif(product_region, '') as region,
        array_agg(DISTINCT product_resourceid) as resource_ids,
        count(DISTINCT product_resourceid) as resource_count,
        max(cost_currencycode) as currency_code,
        sum(cost_mycost) as cost,
        json_parse('{}') as tags
    FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND date(lineitem_intervalusagestart) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND date(lineitem_intervalusagestart) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    GROUP BY date(lineitem_intervalusagestart),
        date(lineitem_intervalusagestart),
        product_service,
        lineitem_tenantid,
        product_region,
        tags_oracle_tags_createdby,
        cost_mycost
)
