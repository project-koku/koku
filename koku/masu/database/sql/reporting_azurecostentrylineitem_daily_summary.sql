-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_azurecostentrylineitem_daily_summary_{uuid} AS (
    SELECT cost_entry_bill_id,
                date(usage_date_time) AS usage_date_time,
                bill.subscription_guid AS subscription_guid, -- account ID
                p.resource_location AS resource_location, -- region
                s.service_name AS service_name, -- service
                s.additional_info->>'ServiceType' as instance_type, -- VM type
                sum(usage_quantity) AS usage_quantity,
                sum(pretax_cost) AS pretax_cost,
                offer_id,
                cost_entry_product_id,
                meter_id,
                service_id,
                tags
    FROM {schema}.reporting_azurecostentrylineitem_daily AS li
    JOIN {schema}.reporting_azurecostentrybill as bill
        ON li.cost_entry_bill_id = bill.id
    JOIN {schema}.reporting_azurecostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    JOIN {schema}.reporting_azureservice AS s
        ON li.service_id = s.id
    WHERE date(li.usage_date_time) >= '{start_date}'
        AND date(li.usage_date_time) <= '{end_date}'
        AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
    GROUP BY date(li.usage_date_time),
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.offer_id,
        li.tags,
        bill.subscription_guid,
        p.resource_location,
        s.service_name, -- service
        s.additional_info->>'ServiceType',
        li.meter_id,
        li.service_id
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
    instance_type
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
        instance_type
    FROM reporting_azurecostentrylineitem_daily_summary_{uuid}
;
