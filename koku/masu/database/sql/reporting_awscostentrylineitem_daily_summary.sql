-- Aggregate tags by summary grouping
CREATE TEMPORARY TABLE aws_tag_summary_{uuid} AS (
    SELECT t.cost_entry_bill_id,
        t.usage_start,
        t.product_code,
        t.product_family,
        t.usage_account_id,
        t.availability_zone,
        t.region,
        t.instance_type,
        t.unit,
        jsonb_object_agg(key, value) as tags
    FROM (
        SELECT li.cost_entry_bill_id,
            li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            li.availability_zone,
            p.region,
            p.instance_type,
            pr.unit,
            key,
            value
        FROM (
            SELECT cost_entry_bill_id,
                usage_start,
                usage_end,
                product_code,
                usage_account_id,
                availability_zone,
                cost_entry_product_id,
                cost_entry_pricing_id,
                key,
                value
            FROM {schema}.reporting_awscostentrylineitem_daily AS li,
                jsonb_each_text(li.tags) tags
        ) li
        JOIN {schema}.reporting_awscostentryproduct AS p
            ON li.cost_entry_product_id = p.id
        LEFT JOIN {schema}.reporting_awscostentrypricing as pr
            ON li.cost_entry_pricing_id = pr.id
        WHERE date(li.usage_start) >= '{start_date}'
            AND date(li.usage_start) <= '{end_date}'
            AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
        GROUP BY li.cost_entry_bill_id,
            li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            li.availability_zone,
            p.region,
            p.instance_type,
            pr.unit,
            key,
            value
    ) t
    GROUP BY t.cost_entry_bill_id,
        t.usage_start,
        t.product_code,
        t.product_family,
        t.usage_account_id,
        t.availability_zone,
        t.region,
        t.instance_type,
        t.unit
)
;

-- Place our query for data with no tags in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_summary_{uuid} AS (
    SELECT li.*,
        CASE WHEN ats.tags IS NOT NULL
            THEN ats.tags
            ELSE '{{}}'::jsonb
            END as tags
    FROM (
        SELECT li.cost_entry_bill_id,
            li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            max(aa.id) as account_alias_id,
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
            array_agg(DISTINCT li.resource_id) as resource_ids,
            count(DISTINCT li.resource_id) as resource_count
        FROM {schema}.reporting_awscostentrylineitem_daily AS li
        JOIN {schema}.reporting_awscostentryproduct AS p
            ON li.cost_entry_product_id = p.id
        LEFT JOIN {schema}.reporting_awscostentrypricing as pr
            ON li.cost_entry_pricing_id = pr.id
        LEFT JOIN {schema}.reporting_awsaccountalias AS aa
            ON li.usage_account_id = aa.account_id
        WHERE date(li.usage_start) >= '{start_date}'
            AND date(li.usage_start) <= '{end_date}'
            AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
        GROUP BY li.cost_entry_bill_id,
            li.usage_start,
            li.usage_end,
            li.product_code,
            p.product_family,
            li.usage_account_id,
            li.availability_zone,
            p.region,
            p.instance_type,
            pr.unit
    ) AS li
    LEFT JOIN aws_tag_summary_{uuid} as ats
        ON li.usage_start = ats.usage_start
            AND (
                li.cost_entry_bill_id = ats.cost_entry_bill_id
                OR (li.cost_entry_bill_id IS NULL AND ats.cost_entry_bill_id IS NULL)
            )
            AND (
                li.product_code = ats.product_code
                OR (li.product_code IS NULL AND ats.product_code IS NULL)
            )
            AND (
                li.product_family = ats.product_family
                OR (li.product_family IS NULL AND ats.product_family IS NULL)
            )
            AND (
                li.usage_account_id = ats.usage_account_id
                OR (li.usage_account_id IS NULL AND ats.usage_account_id IS NULL)
            )
            AND (
                li.availability_zone = ats.availability_zone
                OR (li.availability_zone IS NULL AND ats.availability_zone IS NULL)
            )
            AND (
                li.region = ats.region
                OR (li.region IS NULL AND ats.region IS NULL)
            )
            AND (
                li.instance_type = ats.instance_type
                OR (li.instance_type IS NULL AND ats.instance_type IS NULL)
            )
            AND (
                li.unit = ats.unit
                OR (li.unit IS NULL AND ats.unit IS NULL)
            )
)
;

-- -- Clear out old entries first
DELETE FROM {schema}.reporting_awscostentrylineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cost_entry_bill_id IN ({cost_entry_bill_ids})
;

-- Populate the daily aggregate line item data
INSERT INTO {schema}.reporting_awscostentrylineitem_daily_summary (
    cost_entry_bill_id,
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
    resource_ids,
    resource_count
)
SELECT cost_entry_bill_id,
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
        resource_ids,
        resource_count
    FROM reporting_awscostentrylineitem_daily_summary_{uuid}
;
