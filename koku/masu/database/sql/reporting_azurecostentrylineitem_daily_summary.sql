INSERT INTO {{schema | sqlsafe}}.reporting_azureenabledtagkeys (key)
SELECT DISTINCT(key)
  FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as li, jsonb_each_text(li.tags) labels
 WHERE li.usage_date >= {{start_date}}::date
   AND li.usage_date <= {{end_date}}::date
   AND NOT EXISTS(
         SELECT key
           FROM {{schema | sqlsafe}}.reporting_azureenabledtagkeys
          WHERE key = labels.key
       )
   AND NOT key = ANY(
         SELECT DISTINCT(key)
           FROM {{schema | sqlsafe}}.reporting_azuretags_summary
       )
    --azure_where_clause
   {% if bill_ids %}
   AND li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
       )
   {% endif %}
    ON CONFLICT (key) DO NOTHING;

-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM {{schema | sqlsafe}}.reporting_azureenabledtagkeys
    ),
    cte_filtered_tags AS (
        SELECT id,
            jsonb_object_agg(key,value) as azure_tags
        FROM (
            SELECT lid.id,
                lid.tags as azure_tags,
                aak.key_array
            FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.tags ?| aak.key_array
                AND lid.usage_date >= {{start_date}}::date
                AND lid.usage_date <= {{end_date}}::date
                {% if bill_ids %}
                AND lid.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids  -%}
                        {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%})
                {% endif %}
        ) AS lid,
        jsonb_each_text(lid.azure_tags) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    ),
    cte_split_units AS (
        SELECT li.id,
            m.currency,
            CASE WHEN split_part(m.unit_of_measure, ' ', 2) != '' AND NOT (m.unit_of_measure = '100 Hours' AND m.meter_category='Virtual Machines')
                THEN  split_part(m.unit_of_measure, ' ', 1)::integer
                ELSE 1::integer
                END as multiplier,
            CASE
                WHEN split_part(m.unit_of_measure, ' ', 2) IN ('Hours', 'Hour')
                    THEN  'Hrs'
                WHEN split_part(m.unit_of_measure, ' ', 2) = 'GB/Month'
                    THEN  'GB-Mo'
                WHEN split_part(m.unit_of_measure, ' ', 2) != ''
                    THEN  split_part(m.unit_of_measure, ' ', 2)
                ELSE m.unit_of_measure
            END as unit_of_measure

        FROM {{schema | safe}}.reporting_azurecostentrylineitem_daily AS li
        JOIN {{schema | safe}}.reporting_azuremeter AS m
            ON li.meter_id = m.id
        WHERE li.usage_date >= {{start_date}}::date
            AND li.usage_date <= {{end_date}}::date
            {% if bill_ids %}
            AND li.cost_entry_bill_id IN (
                {%- for bill_id in bill_ids  -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
                {%- endfor -%}
            )
            {% endif %}
    )
    SELECT uuid_generate_v4() as uuid,
        cost_entry_bill_id,
        li.usage_date AS usage_start,
        li.usage_date AS usage_end,
        subscription_guid, -- account ID
        p.resource_location AS resource_location, -- region
        p.service_name AS service_name, -- service
        p.instance_type AS instance_type, -- VM type
        -- Azure meters usage in large blocks e.g. blocks of 100 Hours
        -- We normalize this down to Hours and multiply the usage appropriately
        sum(li.usage_quantity * su.multiplier) AS usage_quantity,
        max(su.unit_of_measure) as unit_of_measure,
        sum(pretax_cost) AS pretax_cost,
        cost_entry_product_id,
        li.meter_id,
        max(su.currency) as currency,
        fvl.azure_tags as tags,
        array_agg(DISTINCT p.instance_id) as instance_ids,
        count(DISTINCT p.instance_id) as instance_count,
        ab.provider_id as source_uuid,
        0.0::decimal as markup_cost
    FROM {{schema | safe}}.reporting_azurecostentrylineitem_daily AS li
    JOIN cte_split_units AS su
        ON li.id = su.id
    LEFT JOIN cte_filtered_tags AS fvl
        ON li.id = fvl.id
    JOIN {{schema | safe}}.reporting_azurecostentryproductservice AS p
        ON li.cost_entry_product_id = p.id
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
        fvl.azure_tags,
        li.subscription_guid,
        p.resource_location,
        li.meter_id,
        p.instance_type,
        p.service_name, -- service
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
    uuid,
    cost_entry_bill_id,
    subscription_guid,
    resource_location,
    service_name,
    meter_id,
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
    source_uuid,
    markup_cost
)
    SELECT uuid,
        cost_entry_bill_id,
        subscription_guid,
        resource_location,
        service_name,
        meter_id,
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
        source_uuid,
        markup_cost
    FROM reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}}
;

-- no need to wait for commit
TRUNCATE TABLE reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_azurecostentrylineitem_daily_summary_{{uuid | sqlsafe}};
