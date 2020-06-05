-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT cost_entry_bill_id,
                li.usage_date AS usage_start,
                li.usage_date AS usage_end,
                subscription_guid, -- account ID
                p.resource_location AS resource_location, -- region
                p.service_name AS service_name, -- service
                p.instance_type AS instance_type, -- VM type
                sum(usage_quantity) AS usage_quantity,
                m.unit_of_measure,
                sum(pretax_cost) AS pretax_cost,
                offer_id,
                cost_entry_product_id,
                li.meter_id,
                m.currency,
                tags,
                array_agg(DISTINCT p.instance_id) as instance_ids,
                count(DISTINCT p.instance_id) as instance_count,
                ab.provider_id as source_uuid
    FROM {{schema | safe}}.reporting_azurecostentrylineitem_daily AS li
    JOIN {{schema | safe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
    JOIN {{schema | safe}}.reporting_azuremeter AS m
        ON li.meter_id = m.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_date >= {{start_date}}::date
        AND li.usage_date <= {{end_date}}::date
        {% if bill_ids %}
        AND li.cost_entry_bill_id IN (
            {%- for bill_id in bill_ids  -%}
            {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%}
        )
        {% endif %}
    GROUP BY li.usage_date,
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.offer_id,
        li.tags,
        li.subscription_guid,
        p.resource_location,
        li.meter_id,
        p.instance_type,
        p.service_name, -- service
        m.currency,
        m.unit_of_measure,
        ab.provider_id
)
;

-- Clear out old entries first
DELETE FROM {{schema | safe}}.reporting_azurecostentrylineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    {% if bill_ids %}
    AND cost_entry_bill_id IN (
        {%- for bill_id in bill_ids  -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
;

-- Populate the daily summary line item data
INSERT INTO {{schema | safe}}.reporting_azurecostentrylineitem_daily_summary (
    cost_entry_bill_id,
    subscription_guid,
    resource_location,
    service_name,
    meter_id,
    offer_id,
    pretax_cost,
    usage_quantity,
    usage_start,
    usage_end,
    tags,
    instance_type,
    currency,
    instance_ids,
    instance_count,
    unit_of_measure,
    source_uuid
)
    SELECT cost_entry_bill_id,
        subscription_guid,
        resource_location,
        service_name,
        meter_id,
        offer_id,
        pretax_cost,
        usage_quantity,
        usage_start,
        usage_end,
        tags,
        instance_type,
        currency,
        instance_ids,
        instance_count,
        unit_of_measure,
        source_uuid
    FROM reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}}
;
