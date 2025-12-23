INSERT INTO {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily_summary (
    uuid,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    subscription_guid,
    resource_location,
    service_name,
    instance_type,
    pretax_cost,
    usage_quantity,
    unit_of_measure,
    currency,
    tags,
    instance_ids,
    instance_count,
    source_uuid,
    markup_cost,
    subscription_name
)
WITH cte_line_items AS (
    SELECT date(date) as usage_date,
        INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
        coalesce(nullif(subscriptionid, ''), subscriptionguid) as subscription_guid,
        resourcelocation as resource_location,
        coalesce(nullif(servicename, ''), metercategory) as service_name,
        (additionalinfo::json->>'ServiceType') as instance_type,
        cast(quantity as DECIMAL(24,9)) as usage_quantity,
        cast(costinbillingcurrency as DECIMAL(24,9)) as pretax_cost,
        coalesce(nullif(billingcurrencycode, ''), billingcurrency) as currency,
        tags::json as tags,
        resourceid as instance_id,
        source::uuid as source_uuid,
        coalesce(nullif(subscriptionname, ''), nullif(subscriptionid, ''), subscriptionguid) as subscription_name,
        CASE
            WHEN split_part(unitofmeasure, ' ', 1) ~ '^\d+(\.\d+)?$' AND NOT (unitofmeasure = '100 Hours' AND metercategory='Virtual Machines') AND NOT split_part(unitofmeasure, ' ', 2) = ''
                THEN cast(split_part(unitofmeasure, ' ', 1) as INTEGER)
            ELSE 1
            END as multiplier,
        CASE
            WHEN split_part(unitofmeasure, ' ', 2) IN ('Hours', 'Hour')
                THEN  'Hrs'
            WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                THEN  'GB-Mo'
            WHEN split_part(unitofmeasure, ' ', 2) != '' AND split_part(unitofmeasure, ' ', 3) = ''
                THEN  split_part(unitofmeasure, ' ', 2)
            ELSE unitofmeasure
        END as unit_of_measure
    FROM {{schema | sqlsafe}}.azure_line_items
    WHERE source = '{{source_uuid | sqlsafe}}'
        AND year = '{{year | sqlsafe}}'
        AND month = '{{month | sqlsafe}}'
        AND date >= '{{start_date | sqlsafe}}'::timestamp
        AND date < '{{end_date | sqlsafe}}'::timestamp + INTERVAL '1 day'
),
cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type = 'Azure'
)
SELECT uuid_generate_v4() as uuid,
    li.usage_date AS usage_start,
    li.usage_date AS usage_end,
    li.cost_entry_bill_id,
    li.subscription_guid, -- account ID
    li.resource_location, -- region
    li.service_name, -- service
    li.instance_type,
    -- Azure meters usage in large blocks e.g. blocks of 100 Hours
    -- We normalize this down to Hours and multiply the usage appropriately
    sum(li.pretax_cost) AS pretax_cost,
    sum(li.usage_quantity * li.multiplier) AS usage_quantity,
    max(li.unit_of_measure) as unit_of_measure,
    max(li.currency) as currency,
    {{schema | sqlsafe}}.filter_json_by_keys(li.tags::text, pek.keys)::json as tags,
    array_agg(DISTINCT li.instance_id) as instance_ids,
    count(DISTINCT li.instance_id) as instance_count,
    li.source_uuid,
    sum(cast(li.pretax_cost * {{markup | sqlsafe}} AS decimal(24,9))) as markup_cost,
    li.subscription_name -- account name
FROM cte_line_items AS li
CROSS JOIN
    cte_pg_enabled_keys as pek
GROUP BY li.usage_date,
    li.cost_entry_bill_id,
    13, -- matches column num for tags map_filter
    li.subscription_guid,
    li.resource_location,
    li.instance_type,
    li.service_name,
    li.source_uuid,
    li.subscription_name
