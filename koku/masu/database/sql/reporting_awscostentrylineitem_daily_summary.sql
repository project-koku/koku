-- Place our query for data with no tags in a temporary table
CREATE TEMPORARY TABLE reporting_awscostentrylineitem_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.cost_entry_bill_id,
        li.usage_start,
        li.usage_end,
        li.product_code,
        p.product_family,
        li.usage_account_id,
        max(aa.id) as account_alias_id,
        li.availability_zone,
        li.tags,
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
        count(DISTINCT li.resource_id) as resource_count,
        max(ou.id) as organizational_unit_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily AS li
    JOIN {{schema | sqlsafe}}.reporting_awscostentryproduct AS p
        ON li.cost_entry_product_id = p.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awscostentrypricing as pr
        ON li.cost_entry_pricing_id = pr.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON li.usage_account_id = aa.account_id
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsorganizationalunit AS ou
        ON aa.id = ou.account_alias_id
            AND ou.created_timestamp <= li.usage_start
            AND (ou.deleted_timestamp is NULL
                 OR ou.deleted_timestamp > li.usage_start)
    WHERE li.usage_start >= {{start_date}}::date
        AND li.usage_start <= {{end_date}}::date
        {% if bill_ids %}
        AND cost_entry_bill_id IN (
            {%- for bill_id in bill_ids  -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%})
        {% endif %}
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
        li.tags
)
;

-- -- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS li
WHERE li.usage_start >= {{start_date}}
    AND li.usage_start <= {{end_date}}
    {% if bill_ids %}
    AND cost_entry_bill_id IN (
        {%- for bill_id in bill_ids  -%}
            {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%})
    {% endif %}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary (
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
    resource_count,
    organizational_unit_id
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
        resource_count,
        organizational_unit_id
    FROM reporting_awscostentrylineitem_daily_summary_{{uuid | sqlsafe}}
;
