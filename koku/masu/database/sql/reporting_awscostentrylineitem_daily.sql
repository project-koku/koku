-- Aggregate tags from hourly to daily level
CREATE TEMPORARY TABLE aws_tag_summary_{uuid} AS (
    SELECT date(t.interval_start) as usage_start,
        cost_entry_bill_id,
        cost_entry_product_id,
        cost_entry_pricing_id,
        cost_entry_reservation_id,
        resource_id,
        line_item_type,
        usage_account_id,
        usage_type,
        operation,
        availability_zone,
        tax_type,
        product_code,
        jsonb_object_agg(t.key, t.value) as tags
    FROM (
        SELECT li.*,
            key,
            value,
            -- Select the most recent value for the key
            row_number() OVER (
                PARTITION BY key,
                    date(interval_start),
                    cost_entry_bill_id,
                    cost_entry_product_id,
                    cost_entry_pricing_id,
                    cost_entry_reservation_id,
                    resource_id,
                    line_item_type,
                    usage_account_id,
                    usage_type,
                    operation,
                    availability_zone,
                    tax_type,
                    product_code
                ORDER BY interval_start desc
            ) as row_number
        FROM (
            SELECT li.*,
                ce.interval_start
            FROM reporting_awscostentrylineitem AS li
            JOIN reporting_awscostentry AS ce
                ON li.cost_entry_id = ce.id
            WHERE date(ce.interval_start) >= '{start_date}'
                AND date(ce.interval_start) <= '{end_date}'
                AND li.cost_entry_bill_id IN ({cost_entry_bill_ids})
        ) li,
        jsonb_each_text(li.tags) tags
    ) t
    WHERE t.row_number = 1
    GROUP BY date(t.interval_start),
        t.cost_entry_bill_id,
        t.cost_entry_product_id,
        t.cost_entry_pricing_id,
        t.cost_entry_reservation_id,
        t.resource_id,
        t.line_item_type,
        t.usage_account_id,
        t.usage_type,
        t.operation,
        t.availability_zone,
        t.tax_type,
        t.product_code
)
;

-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_{uuid} AS (
    SELECT li.*,
        CASE WHEN ats.tags IS NOT NULL
            THEN ats.tags
            ELSE '{{}}'::jsonb
            END as tags
    FROM (
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
        FROM reporting_awscostentrylineitem AS li
        JOIN reporting_awscostentry AS ce
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
            li.product_code
    ) AS li
    LEFT JOIN aws_tag_summary_{uuid} AS ats
        ON  li.usage_start = ats.usage_start
                AND (
                    li.cost_entry_bill_id = ats.cost_entry_bill_id
                    OR (li.cost_entry_bill_id IS NULL AND ats.cost_entry_bill_id IS NULL)
                )
                AND (
                    li.cost_entry_product_id = ats.cost_entry_product_id
                    OR (li.cost_entry_product_id IS NULL AND ats.cost_entry_product_id IS NULL)
                )
                AND (
                    li.cost_entry_pricing_id = ats.cost_entry_pricing_id
                    OR (li.cost_entry_pricing_id IS NULL AND ats.cost_entry_pricing_id IS NULL)
                )
                AND (
                    li.cost_entry_reservation_id = ats.cost_entry_reservation_id
                    OR (li.cost_entry_reservation_id IS NULL AND ats.cost_entry_reservation_id IS NULL)
                )
                AND (
                    li.line_item_type = ats.line_item_type
                    OR (li.line_item_type IS NULL AND ats.line_item_type IS NULL)
                )
                AND (
                    li.usage_account_id = ats.usage_account_id
                    OR (li.usage_account_id IS NULL AND ats.usage_account_id IS NULL)
                )
                AND (
                    li.usage_type = ats.usage_type
                    OR (li.usage_type IS NULL AND ats.usage_type IS NULL)
                )
                AND (
                    li.operation = ats.operation
                    OR (li.operation IS NULL AND ats.operation IS NULL)
                )
                AND (
                    li.availability_zone = ats.availability_zone
                    OR (li.availability_zone IS NULL AND ats.availability_zone IS NULL)
                )
                AND (
                    li.resource_id = ats.resource_id
                    OR (li.resource_id IS NULL AND ats.resource_id IS NULL)
                )
                AND (
                    li.tax_type = ats.tax_type
                    OR (li.tax_type IS NULL AND ats.tax_type IS NULL)
                )
                AND (
                    li.product_code = ats.product_code
                    OR (li.product_code IS NULL AND ats.product_code IS NULL)
                )
)
;

-- Clear out old entries first
DELETE FROM reporting_awscostentrylineitem_daily
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cost_entry_bill_id IN ({cost_entry_bill_ids})
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_awscostentrylineitem_daily (
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
