-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_summary_{uuid} AS (
    SELECT li.usage_start,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        li.availability_zone,
        p.region,
        p.instance_type,
        pr.unit,
        sum(li.usage_amount) as usage_amount,
        max(li.normalization_factor) as normalization_factor,
        sum(li.normalized_usage_amount) as normalized_usage_amount,
        max(li.currency_code) as currency_code,
        max(li.unblended_rate) as unblended_rate,
        sum(li.unblended_cost) as unblended_cost,
        max(li.blended_rate) as blended_rate,
        sum(li.blended_cost) as blended_cost,
        sum(li.public_on_demand_cost) as public_on_demand_cost,
        max(li.public_on_demand_rate) as public_on_demand_rate,
        count(DISTINCT li.resource_id) as resource_count
    FROM reporting_awscostentrylineitem_daily AS li
    JOIN reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    WHERE li.usage_start >= '{start_date}'
        AND li.usage_start <= '{end_date}'
    GROUP BY li.usage_start,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        li.availability_zone,
        p.region,
        p.instance_type,
        pr.unit
)
;

-- Clear out old entries first
DELETE FROM reporting_awscostentrylineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}';

-- Populate the daily aggregate line item data
INSERT INTO reporting_awscostentrylineitem_daily_summary (
    usage_start,
    product_code,
    product_family,
    usage_account_id,
    availability_zone,
    region,
    instance_type,
    unit,
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
    resource_count
)
    SELECT usage_start,
        product_code,
        product_family,
        usage_account_id,
        availability_zone,
        region,
        instance_type,
        unit,
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
        resource_count
    FROM reporting_awscostentrylineitem_daily_summary_{uuid}
;
