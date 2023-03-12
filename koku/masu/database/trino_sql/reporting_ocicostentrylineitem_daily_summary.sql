INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary (
    uuid,
    cost_entry_bill_id,
    usage_start,
    usage_end,
    payer_tenant_id,
    product_service,
    region,
    instance_type,
    resource_ids,
    resource_count,
    usage_amount,
    unit,
    currency,
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
    cast(payer_tenant_id AS varchar(80)),
    cast(product_service AS varchar(50)),
    cast(region AS varchar(50)),
    CASE
        WHEN product_service = 'COMPUTE' THEN instance_type
        ELSE NULL
    END AS instance_type,
    resource_ids,
    cast(resource_count AS integer),
    cast(CASE
        WHEN unit = 'MS' THEN usage_amount / 3600000.0
        WHEN unit = 'BYTES' THEN usage_amount / (
                cast(day(last_day_of_month(date(usage_start))) as integer)
            ) *
            power(2, -30)
        WHEN unit = 'BYTE_MS' THEN usage_amount / 1000.0 / (
            86400.0 *
            cast(extract(day from last_day_of_month(date(usage_start))) as integer)
            ) *
            power(2, -30)
        WHEN unit = 'GB_MS' THEN usage_amount / 1000.0 / (
            86400.0 *
            cast(extract(day from last_day_of_month(date(usage_start))) as integer)
            )
        ELSE usage_amount
    END AS decimal(24,9)) AS usage_amount,
    CASE
        WHEN unit = 'MS' THEN  'Hrs'
        WHEN unit = 'BYTES' THEN  'GB-Mo'
        WHEN unit = 'BYTE_MS' THEN  'GB-Mo'
        WHEN unit = 'GB_MS' THEN  'GB-Mo'
        ELSE unit
    END as unit,
    cast(currency AS varchar(10)),
    cast(cost AS decimal(24,9)),
    cast(
        map_filter(
            cast(json_parse(tags) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
     ) as tags,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    cast(cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost
FROM (
    SELECT date(c.lineitem_intervalusagestart) as usage_start,
        date(c.lineitem_intervalusagestart) as usage_end,
        c.lineitem_tenantid as payer_tenant_id,
        nullif(c.product_service, '') as product_service,
        nullif(c.product_region, '') as region,
        nullif(u.product_resource, '') as instance_type,
        array_agg(DISTINCT c.product_resourceid) as resource_ids,
        count(DISTINCT c.product_resourceid) as resource_count,
        sum(u.usage_consumedquantity) as usage_amount,
        nullif(u.usage_consumedquantityunits, '') as unit,
        max(c.cost_currencycode) as currency,
        sum(c.cost_mycost) as cost,
        c.tags as tags
    FROM hive.{{schema | sqlsafe}}.oci_cost_line_items as c
    JOIN hive.{{schema | sqlsafe}}.oci_usage_line_items as u
        ON c.lineItem_intervalUsageStart = u.lineItem_intervalUsageStart
        AND c.product_resourceId = u.product_resourceId
    WHERE c.source = '{{source_uuid | sqlsafe}}'
        AND c.year = '{{year | sqlsafe}}'
        AND c.month = '{{month | sqlsafe}}'
        AND date(c.lineitem_intervalusagestart) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND date(c.lineitem_intervalusagestart) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    GROUP BY date(c.lineitem_intervalusagestart),
        c.product_service,
        c.lineitem_tenantid,
        c.product_region,
        c.tags,
        c.cost_mycost,
        u.product_resource,
        u.usage_consumedquantityunits
) AS ds
CROSS JOIN cte_pg_enabled_keys AS pek
;
