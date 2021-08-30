-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_gcpcostentrylineitem_daily_{{uuid | sqlsafe}} AS (
    SELECT date(li.usage_start) as usage_start,
        date(li.usage_start) as usage_end,
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.project_id,
        li.line_item_type,
        li.usage_type,
        li.tags,
        li.region,
        sum(li.cost) as cost,
        li.currency,
        li.conversion_rate,
        sum(li.usage_to_pricing_units) as usage_in_pricing_units,
        li.usage_pricing_unit,
        li.invoice_month,
        li.cost_type as tax_type
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem AS li
    WHERE date(li.partition_date) >= {{ start_date }}
        AND date(li.partition_date) <= {{ end_date }}
        {% if bill_ids %}
        AND cost_entry_bill_id IN (
            {%- for bill_id in bill_ids  -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%})
        {% endif %}
    GROUP BY date(li.usage_start),
        li.cost_entry_bill_id,
        li.cost_entry_product_id,
        li.project_id,
        li.line_item_type,
        li.usage_type,
        li.tags,
        li.region,
        li.currency,
        li.conversion_rate,
        li.usage_pricing_unit,
        li.invoice_month,
        li.cost_type
)
;

-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily AS li
WHERE li.partition_date >= {{start_date}}
    AND li.partition_date <= {{end_date}}
    {% if bill_ids %}
    AND cost_entry_bill_id IN (
        {%- for bill_id in bill_ids  -%}
            {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%})
    {% endif %}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily (
    cost_entry_bill_id,
    cost_entry_product_id,
    project_id,
    line_item_type,
    usage_start,
    usage_end,
    tags,
    usage_type,
    region,
    cost,
    currency,
    conversion_rate,
    usage_in_pricing_units,
    usage_pricing_unit,
    invoice_month,
    tax_type
)
    SELECT cost_entry_bill_id,
    cost_entry_product_id,
    project_id,
    line_item_type,
    usage_start,
    usage_end,
    tags,
    usage_type,
    region,
    cost,
    currency,
    conversion_rate,
    usage_in_pricing_units,
    usage_pricing_unit,
    invoice_month,
    tax_type
    FROM reporting_gcpcostentrylineitem_daily_{{uuid | sqlsafe}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_gcpenabledtagkeys (key)
SELECT DISTINCT(key)
  FROM reporting_gcpcostentrylineitem_daily_{{uuid | sqlsafe}} as li,
       jsonb_each_text(li.tags) labels
 WHERE NOT EXISTS(
        SELECT key
          FROM {{schema | sqlsafe}}.reporting_gcpenabledtagkeys
         WHERE key = labels.key
       )
   AND NOT key = ANY(
         SELECT DISTINCT(key)
           FROM {{schema | sqlsafe}}.reporting_gcptags_summary
       )
    ON CONFLICT (key) DO NOTHING;

TRUNCATE TABLE reporting_gcpcostentrylineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_gcpcostentrylineitem_daily_{{uuid | sqlsafe}};
