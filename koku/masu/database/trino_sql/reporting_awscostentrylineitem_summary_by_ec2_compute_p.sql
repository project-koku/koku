INSERT INTO postgres.{{schema | sqlsafe}}.reporting_awscostentrylineitem_summary_by_ec2_compute_p (
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
),
cte_latest_values as (
    SELECT
        lineitem_resourceid as resource_id,
        nullif(product_instancetype, '') as instance_type,
        max(json_extract_scalar(json_parse(resourcetags), '$.Name')) AS instance_name,
        ARRAY_AGG(resourcetags) as tags,
        ARRAY_AGG(costcategory) as cost_category
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily as alid
    WHERE source = '{{source_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND lineitem_productcode = 'AmazonEC2'
    AND product_productfamily LIKE '%Compute Instance%'
    AND lineitem_resourceid != ''
    AND lineitem_usagestartdate = (
        SELECT max(date(lv.lineitem_usagestartdate)) as usage_start from hive.{{schema | sqlsafe}}.aws_line_items_daily as lv
    )
    GROUP BY
        lineitem_resourceid,
        product_instancetype
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
            cast(json_parse(tags[1]) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
    ) as tags,
    cast(json_parse(cost_category[1]) as json) as cost_category,
    unit,
    cast(usage_amount as decimal(24,9)) as usage_amount,
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
       max(lineitem_usageaccountid) as usage_account_id,
       lineitem_resourceid as resource_id,
       max(json_extract_scalar(json_parse(resourcetags), '$.Name')) AS instance_name,
       max(cte_l.instance_type) as instance_type,
       max(nullif(product_operatingsystem, '')) as operating_system,
       max(nullif(product_region, '')) as region,
       max(cast(nullif(product_vcpu, '') AS INTEGER)) as vcpu,
       max(nullif(product_memory, '')) as memory,
       max(cte_l.tags) as tags,
       max(cte_l.cost_category) as cost_category,
       max(nullif(pricing_unit, '')) as unit,
       -- SavingsPlanNegation needs to be negated to prevent duplicate usage COST-5369
       sum(
           CASE
               WHEN lineitem_lineitemtype='SavingsPlanNegation'
               THEN 0.0
               ELSE lineitem_usageamount
           END
       ) as usage_amount,
       max(lineitem_normalizationfactor) as normalization_factor,
       sum(lineitem_normalizedusageamount) as normalized_usage_amount,
       max(lineitem_currencycode) as currency_code,
       max(lineitem_unblendedrate) as unblended_rate,
       /* SavingsPlanCoveredUsage entries have corresponding SavingsPlanNegation line items
           that offset that cost.
           https://docs.aws.amazon.com/cur/latest/userguide/cur-sp.html
       */
       sum(
           CASE
               WHEN lineitem_lineitemtype='SavingsPlanCoveredUsage'
               THEN 0.0
               ELSE lineitem_unblendedcost
           END
       ) as unblended_cost,
       max(lineitem_blendedrate) as blended_rate,
        /* SavingsPlanCoveredUsage entries have corresponding SavingsPlanNegation line items
           that offset that cost.
           https://docs.aws.amazon.com/cur/latest/userguide/cur-sp.html
        */
       sum(
           CASE
               WHEN lineitem_lineitemtype='SavingsPlanCoveredUsage'
               THEN 0.0
               ELSE lineitem_blendedcost
           END
       ) as blended_cost,
       sum(savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
       sum(
           CASE
               WHEN lineitem_lineitemtype='Tax'
               OR lineitem_lineitemtype='Usage'
               THEN lineitem_unblendedcost
               ELSE savingsplan_savingsplaneffectivecost
           END
       ) as calculated_amortized_cost,
       sum(pricing_publicondemandcost) as public_on_demand_cost,
       max(pricing_publicondemandrate) as public_on_demand_rate
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily as lid
        JOIN cte_latest_values AS cte_l
        ON lid.lineitem_resourceid = cte_l.resource_id
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND lineitem_productcode = 'AmazonEC2'
        AND product_productfamily LIKE '%Compute Instance%'
        AND lineitem_resourceid != ''
    GROUP BY lineitem_resourceid
) AS ds
CROSS JOIN cte_pg_enabled_keys AS pek
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON ds.usage_account_id = aa.account_id
