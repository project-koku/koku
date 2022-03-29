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
    usage_consumedquantity,
    consumedquantityunits,
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
    cast(usage_consumedquantity AS decimal(24,9)),
    consumedquantityunits,
    cast(currency_code AS varchar(10)),
    cast(cost AS decimal(24,9)),
    tags,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    cast(cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost
FROM (
    SELECT date(c.lineitem_intervalusagestart) as usage_start,
        date(c.lineitem_intervalusagestart) as usage_end,
        c.lineitem_tenantid as payer_tenant_id,
        nullif(c.product_service, '') as product_service,
        nullif(c.product_region, '') as region,
        array_agg(DISTINCT c.product_resourceid) as resource_ids,
        count(DISTINCT c.product_resourceid) as resource_count,
        sum(u.usage_consumedquantity) as usage_consumedquantity,
        nullif(u.consumedquantityunits, '') as consumedquantityunits,
        max(c.cost_currencycode) as currency_code,
        sum(c.cost_mycost) as cost,
        json_parse('{}') as tags
    FROM hive.{{schema | sqlsafe}}.oci_cost_line_items as c
    JOIN hive.{{schema | sqlsafe}}.oci_usage_line_items as u
        ON c.lineItem_intervalUsageStart = u.lineItem_intervalUsageStart
        AND c.product_resourceId = u.product_resourceId
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND date(c.lineitem_intervalusagestart) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND date(c.lineitem_intervalusagestart) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    GROUP BY date(c.lineitem_intervalusagestart),
        c.product_service,
        c.lineitem_tenantid,
        c.product_region,
        c.tags_oracle_tags_createdby,
        c.cost_mycost
)
