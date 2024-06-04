INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awscostentrylineitem_summary_by_ec2_compute (
    uuid,
    usage_start,
    usage_end,
    usage_account_id,
    resource_id,
    instance_name,
    instance_type,
    operating_system,
    region,
    vcpu,
    memory,
    tags,
    cost_category,
    unit,
    usage_amount,
    normalization_factor,
    normalized_usage_amount,
    currency_code,
    unblended_rate,
    unblended_cost,
    markup_cost,
    blended_rate,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    calculated_amortized_cost,
    markup_cost_amortized,
    public_on_demand_cost,
    public_on_demand_rate,
    source_uuid,
    cost_entry_bill_id,
    account_alias_id
)
with cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type = 'AWS'
)
SELECT uuid() as uuid,
    usage_start,
    usage_end,
    cast(usage_account_id AS varchar(50)),
    resource_id,
    instance_name,
    instance_type,
    operating_system,
    region,
    vcpu,
    memory,
    cast(
        map_filter(
            cast(json_parse(tags) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
     ) as tags,
    json_parse(costcategory) as cost_category,
    unit,
    cast(usage_amount AS decimal(24,9)),
    normalization_factor,
    normalized_usage_amount,
    cast(currency_code AS varchar(10)),
    cast(unblended_rate AS decimal(24,9)),
    cast(unblended_cost AS decimal(24,9)),
    cast(unblended_cost * {{markup | sqlsafe}} AS decimal(24,9)) as markup_cost,
    cast(blended_rate AS decimal(24,9)),
    cast(blended_cost AS decimal(24,9)),
    cast(blended_cost * {{markup | sqlsafe}} AS decimal(33,15)) as markup_cost_blended,
    cast(savingsplan_effective_cost AS decimal(24,9)),
    cast(savingsplan_effective_cost * {{markup | sqlsafe}} AS decimal(33,15)) as markup_cost_savingsplan,
    cast(calculated_amortized_cost AS decimal(33, 9)),
    cast(calculated_amortized_cost * {{markup | sqlsafe}} AS decimal(33,9)) as markup_cost_amortized,
    cast(public_on_demand_cost AS decimal(24,9)),
    cast(public_on_demand_rate AS decimal(24,9)),
    UUID '{{source_uuid | sqlsafe}}' as source_uuid,
    INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
    aa.id as account_alias_id
FROM (
    SELECT min(date(lineitem_usagestartdate)) as usage_start,
        max(date(lineitem_usagestartdate)) as usage_end,
        lineitem_usageaccountid as usage_account_id,
        lineitem_resourceid as resource_id,
        json_extract_scalar(json_parse(resourcetags), '$.Name') AS instance_name,
        nullif(product_instancetype, '') as instance_type,
        nullif(product_operatingsystem, '') as operating_system,
        nullif(product_region, '') as region,
        cast(nullif(product_vcpu, '') AS INTEGER) as vcpu,
        nullif(product_memory, '') as memory,
        resourcetags as tags,
        costcategory,
        nullif(pricing_unit, '') as unit,
        sum(lineitem_usageamount) as usage_amount,
        max(lineitem_normalizationfactor) as normalization_factor,
        sum(lineitem_normalizedusageamount) as normalized_usage_amount,
        max(lineitem_currencycode) as currency_code,
        max(lineitem_unblendedrate) as unblended_rate,
        sum(lineitem_unblendedcost) as unblended_cost,
        max(lineitem_blendedrate) as blended_rate,
        sum(lineitem_blendedcost) as blended_cost,
        sum(savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
        sum(
            CASE
                WHEN lineitem_lineitemtype='Tax'
                OR   lineitem_lineitemtype='Usage'
                THEN lineitem_unblendedcost
                ELSE savingsplan_savingsplaneffectivecost
            END
        ) as calculated_amortized_cost,
        sum(pricing_publicondemandcost) as public_on_demand_cost,
        max(pricing_publicondemandrate) as public_on_demand_rate

    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND lineitem_productcode = 'AmazonEC2'
        AND product_productfamily LIKE '%Compute%'
    GROUP BY lineitem_resourceid,
        lineitem_usageaccountid,
        product_instancetype,
        product_operatingsystem,
        product_region,
        product_memory,
        product_vcpu,
        resourcetags,
        costcategory,
        pricing_unit
) AS ds
CROSS JOIN cte_pg_enabled_keys AS pek
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON ds.usage_account_id = aa.account_id
