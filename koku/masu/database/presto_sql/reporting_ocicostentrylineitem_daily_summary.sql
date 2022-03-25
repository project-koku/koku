INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary (
    uuid,
    cost_entry_bill_id,
    usage_start,
    usage_end,
    payer_tenant_id,
    product_code,
    region,
    instance_type,
    unit,
    resource_ids,
    resource_count,
    usage_amount,
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
    cast(product_code AS varchar(50)),
    region,
    instance_type,
    unit,
    resource_ids,
    resource_count,
    cast(usage_amount AS decimal(24,9)),
    cast(currency_code AS varchar(10)),
    cast(cost AS decimal(24,9)),
    cast(
        map_filter(
            cast(json_parse(tags) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
     ) as tags,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    cast(unblended_cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost
FROM (
    SELECT date(lineitem_intervalusagestart) as usage_start,
        date(lineitem_intervalusageend) as usage_end,
        nullif(product_service, '') as product_code,
        lineitem_tenantid as payer_tenant_id,
        nullif(product_region, '') as region,
        tags,
        nullif(product_resource, '') as instance_type,
        nullif(usage_consumedquantityunits, '') as unit,
        sum(usage_consumedquantity) as usage_amount,
        max(cost_currencycode) as currency_code,
        sum(cost_mycost) as cost,
        array_agg(DISTINCT product_resourceid) as resource_ids,
        count(DISTINCT product_resourceid) as resource_count
    FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND lineitem_intervalusagestart >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND lineitem_intervalusagestart < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    GROUP BY date(lineitem_usagestartdate),
        lineitem_productcode,
        lineitem_tenantid,
        product_region,
        resourcetags,
        product_instancetype,
        pricing_unit
)
