CREATE TABLE hive.{{schema | sqlsafe}}.presto_aws_daily_summary_{{uuid | sqlsafe}} AS (
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
    WHERE date(lineitem_usagestartdate) >= date('{{start_date | sqlsafe}}')
        AND date(lineitem_usagestartdate) <= date('{{end_date | sqlsafe}}')
        -- TODO: ADD partitions year and month to this
    GROUP BY date(lineitem_usagestartdate),
        lineitem_productcode,
        lineitem_usageaccountid,
        lineitem_availabilityzone,
        product_productfamily,
        product_region,
        resourcetags,
        product_instancetype,
        pricing_unit
)
