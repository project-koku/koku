-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_azurecostentrylineitem_daily_summary_{uuid} AS (
    SELECT cost_entry_bill_id,
                date(usage_date_time) AS usage_date_time,
                subscription_guid, -- account ID
                p.resource_location AS resource_location, -- region
                p.service_name AS service_name, -- service
                p.additional_info->>'ServiceType' as instance_type, -- VM type
                sum(usage_quantity) AS usage_quantity,
                sum(pretax_cost) AS pretax_cost,
                offer_id,
                cost_entry_product_id,
                li.meter_id,
                m.currency,
                tags,
                array_agg(DISTINCT p.instance_id) as instance_ids,
                count(DISTINCT p.instance_id) as instance_count
    FROM {schema}.reporting_azurecostentrylineitem_daily AS li
    JOIN {schema}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {schema}.reporting_azuremeter AS m
        ON li.meter_id = m.id
    WHERE date(li.usage_date_time) >= '{start_date}'
        AND date(li.usage_date_time) <= '{end_date}'
        AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
    GROUP BY date(li.usage_date_time),
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.offer_id,
        li.tags,
        li.subscription_guid,
        p.resource_location,
        li.meter_id,
        p.additional_info->>'ServiceType',
        p.service_name, -- service
        m.currency
)
;

-- Clear out old entries first
DELETE FROM {schema}.reporting_azurecostentrylineitem_daily_summary
WHERE usage_date_time >= '{start_date}'
    AND usage_date_time <= '{end_date}'
    AND cost_entry_bill_id IN ({cost_entry_bill_ids})
;

-- Populate the daily summary line item data
INSERT INTO {schema}.reporting_azurecostentrylineitem_daily_summary (
    cost_entry_bill_id,
    subscription_guid,
    resource_location,
    service_name,
    meter_id,
    offer_id,
    pretax_cost,
    usage_quantity,
    usage_date_time,
    tags,
    instance_type,
    currency,
    instance_ids,
    instance_count
)
    SELECT cost_entry_bill_id,
        subscription_guid,
        resource_location,
        service_name,
        meter_id,
        offer_id,
        pretax_cost,
        usage_quantity,
        usage_date_time,
        tags,
        instance_type,
        currency,
        instance_ids,
        instance_count
    FROM reporting_azurecostentrylineitem_daily_summary_{uuid}
;
