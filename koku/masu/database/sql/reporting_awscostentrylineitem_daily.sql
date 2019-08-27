-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_{uuid} AS (
    SELECT date(ce.interval_start) as usage_start,
        date(ce.interval_start) as usage_end,
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.cost_entry_pricing_id,
        li.cost_entry_reservation_id,
        li.line_item_type,
        li.usage_account_id,
        li.usage_type,
        li.operation,
        li.availability_zone,
        li.resource_id,
        li.tax_type,
        li.product_code,
        li.tags,
        sum(li.usage_amount) as usage_amount,
        max(li.normalization_factor) as normalization_factor,
        sum(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_rate) as unblended_rate,
        sum(li.unblended_cost) as unblended_cost,
        max(li.blended_rate) as blended_rate,
        sum(li.blended_cost) as blended_cost,
        sum(li.public_on_demand_cost) as public_on_demand_cost,
        max(li.public_on_demand_rate) as public_on_demand_rate
    FROM {schema}.reporting_awscostentrylineitem AS li
    JOIN {schema}.reporting_awscostentry AS ce
        ON li.cost_entry_id = ce.id
    WHERE date(ce.interval_start) >= '{start_date}'
        AND date(ce.interval_start) <= '{end_date}'
        AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
    GROUP BY date(ce.interval_start),
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.cost_entry_pricing_id,
        li.cost_entry_reservation_id,
        li.resource_id,
        li.line_item_type,
        li.usage_account_id,
        li.usage_type,
        li.operation,
        li.availability_zone,
        li.tax_type,
        li.product_code,
        li.tags
)
;

-- Clear out old entries first
DELETE FROM {schema}.reporting_awscostentrylineitem_daily
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cost_entry_bill_id IN ({cost_entry_bill_ids})
;

-- Populate the daily aggregate line item data
INSERT INTO {schema}.reporting_awscostentrylineitem_daily (
    usage_start,
    usage_end,
    cost_entry_bill_id,
    cost_entry_product_id,
    cost_entry_pricing_id,
    cost_entry_reservation_id,
    line_item_type,
    usage_account_id,
    usage_type,
    operation,
    availability_zone,
    resource_id,
    tax_type,
    product_code,
    tags,
    usage_amount,
    normalization_factor,
    normalized_usage_amount,
    currency_code,
    unblended_rate,
    unblended_cost,
    blended_rate,
    blended_cost,
    public_on_demand_cost,
    public_on_demand_rate
)
    SELECT usage_start,
        usage_end,
        cost_entry_bill_id,
        cost_entry_product_id,
        cost_entry_pricing_id,
        cost_entry_reservation_id,
        line_item_type,
        usage_account_id,
        usage_type,
        operation,
        availability_zone,
        resource_id,
        tax_type,
        product_code,
        tags,
        usage_amount,
        normalization_factor,
        normalized_usage_amount,
        currency_code,
        unblended_rate,
        unblended_cost,
        blended_rate,
        blended_cost,
        public_on_demand_cost,
        public_on_demand_rate
    FROM reporting_awscostentrylineitem_daily_{uuid}
;
