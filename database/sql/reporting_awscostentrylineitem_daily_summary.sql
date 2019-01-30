-- Place our query for data with no tags in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_summary_{uuid} AS (
    SELECT li.usage_start,
        li.usage_end,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.availability_zone,
        p.region,
        p.instance_type,
        pr.unit,
        '{{}}'::jsonb as tags,
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
    LEFT JOIN reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    WHERE date(li.usage_start) >= '{start_date}'
        AND date(li.usage_start) <= '{end_date}'
    GROUP BY li.usage_start,
        li.usage_end,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        li.availability_zone,
        p.region,
        p.instance_type,
        pr.unit
    UNION
    SELECT usage_start,
        usage_end,
        product_code,
        product_family,
        usage_account_id,
        account_alias_id,
        availability_zone,
        region,
        instance_type,
        unit,
        cast(concat('{{"', key, '": "', value, '"}}') as jsonb) as tags,
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
    FROM (
        SELECT li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            max(aa.id) as account_alias_id,
            li.availability_zone,
            p.region,
            p.instance_type,
            pr.unit,
            li.key,
            li.value,
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
        FROM (
            SELECT usage_start,
                usage_end,
                product_code,
                usage_account_id,
                availability_zone,
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
                resource_id,
                cost_entry_product_id,
                cost_entry_pricing_id,
                key,
                value
            FROM reporting_awscostentrylineitem_daily AS li,
                jsonb_each_text(li.tags) tags
        ) li
        JOIN reporting_awscostentryproduct AS p
            ON li.cost_entry_product_id = p.id
        LEFT JOIN reporting_awscostentrypricing as pr
            ON li.cost_entry_pricing_id = pr.id
        LEFT JOIN reporting_awsaccountalias AS aa
            ON li.usage_account_id = aa.account_id
        WHERE date(li.usage_start) >= '{start_date}'
            AND date(li.usage_start) <= '{end_date}'
        GROUP BY li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            li.availability_zone,
            p.region,
            p.instance_type,
            pr.unit,
            li.key,
            li.value
    ) t
)
;

-- -- Clear out old entries first
DELETE FROM reporting_awscostentrylineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}';

-- Populate the daily aggregate line item data
INSERT INTO reporting_awscostentrylineitem_daily_summary (
    usage_start,
    usage_end,
    product_code,
    product_family,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    instance_type,
    unit,
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
    public_on_demand_rate,
    resource_count
)
    SELECT usage_start,
        usage_end,
        product_code,
        product_family,
        usage_account_id,
        account_alias_id,
        availability_zone,
        region,
        instance_type,
        unit,
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
        public_on_demand_rate,
        resource_count
    FROM reporting_awscostentrylineitem_daily_summary_{uuid}
;
