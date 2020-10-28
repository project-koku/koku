INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary (
    uuid,
    usage_start,
    usage_end,
    usage_account_id,
    availability_zone,
    resource_ids,
    product_code,
    usage_amount,
    normalization_factor,
    normalized_usage_amount,
    currency_code,
    unblended_rate,
    unblended_cost,
    blended_rate,
    blended_cost,
    public_on_demand_cost,
    public_on_demand_rate,
    tags,
    account_alias_id,
    organizational_unit_id,
    source_uuid,
    cost_entry_bill_id,
    markup_cost
)
SELECT uuid() as uuid,
    usage_start,
    usage_end,
    cast(usage_account_id AS varchar(50)),
    cast(availability_zone AS varchar(50)),
    resource_ids,
    cast(product_code AS varchar(50)),
    cast(usage_amount AS decimal(24,9)),
    normalization_factor,
    normalized_usage_amount,
    cast(currency_code AS varchar(10)),
    cast(unblended_rate AS decimal(24,9)),
    cast(unblended_cost AS decimal(24,9)),
    cast(blended_rate AS decimal(24,9)),
    cast(blended_cost AS decimal(24,9)),
    cast(public_on_demand_cost AS decimal(24,9)),
    cast(public_on_demand_rate AS decimal(24,9)),
    json_parse(tags) as tags,
    aa.id as account_alias_id,
    ou.id as organizational_unit_id,
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
    cast(unblended_cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost
FROM (
    SELECT date(lineitem_usagestartdate) as usage_start,
        date(lineitem_usagestartdate) as usage_end,
        lineitem_productcode as product_code,
        product_productfamily as product_family,
        lineitem_usageaccountid as usage_account_id,
        lineitem_availabilityzone as availability_zone,
        product_region as region,
        resourcetags as tags,
        product_instancetype as instance_type,
        pricing_unit as unit,
        sum(lineitem_usageamount) as usage_amount,
        max(lineitem_normalizationfactor) as normalization_factor,
        sum(lineitem_normalizedusageamount) as normalized_usage_amount,
        max(lineitem_currencycode) as currency_code,
        max(lineitem_unblendedrate) as unblended_rate,
        sum(lineitem_unblendedcost) as unblended_cost,
        max(lineitem_blendedrate) as blended_rate,
        sum(lineitem_blendedcost) as blended_cost,
        sum(pricing_publicondemandcost) as public_on_demand_cost,
        max(pricing_publicondemandrate) as public_on_demand_rate,
        array_agg(DISTINCT lineitem_resourceid) as resource_ids
    FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND date(lineitem_usagestartdate) >= date('{{start_date | sqlsafe}}')
        AND date(lineitem_usagestartdate) <= date('{{end_date | sqlsafe}}')
    GROUP BY date(lineitem_usagestartdate),
        lineitem_productcode,
        lineitem_usageaccountid,
        lineitem_availabilityzone,
        product_productfamily,
        product_region,
        resourcetags,
        product_instancetype,
        pricing_unit
) AS ds
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON ds.usage_account_id = aa.account_id
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsorganizationalunit AS ou
    ON aa.id = ou.account_alias_id
        AND ou.created_timestamp <= ds.usage_start
        AND (
            ou.deleted_timestamp is NULL
            OR ou.deleted_timestamp > ds.usage_start
        )
