CREATE TEMPORARY TABLE reporting_gcpcostentrylineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM {{schema | sqlsafe}}.reporting_gcpenabledtagkeys
    ),
    cte_filtered_tags AS (
        SELECT id,
            jsonb_object_agg(key,value) as gcp_tags
        FROM (
            SELECT lid.id,
                lid.tags as gcp_tags,
                aak.key_array
            FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.tags ?| aak.key_array
                AND lid.usage_start >= {{start_date}}::date
                AND lid.usage_start <= {{end_date}}::date
                {% if bill_ids %}
                AND lid.cost_entry_bill_id IN (
                    {%- for bill_id in bill_ids  -%}
                        {{bill_id}}{% if not loop.last %},{% endif %}
                    {%- endfor -%})
                {% endif %}
        ) AS lid,
        jsonb_each_text(lid.gcp_tags) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    )
    SELECT uuid_generate_v4() as uuid,
        li.cost_entry_bill_id,
        pj.account_id,
        pj.project_id,
        pj.project_name,
        ps.service_id,
        ps.service_alias,
        ps.sku_id,
        ps.sku_alias,
        li.usage_start,
        li.usage_end,
        li.line_item_type,
        li.usage_type as instance_type,
        SUM(case when li.usage_in_pricing_units = 'NaN' then 0.0::numeric(24,9) else li.usage_in_pricing_units end::numeric(24,9)) AS usage_amount,
        fvl.gcp_tags as tags,
        case when li.region = 'nan' then NULL else li.region end as region,
        sum(li.cost) as unblended_cost,
        li.usage_pricing_unit as unit,
        li.currency,
        ab.provider_id as source_uuid,
        0.0::decimal as markup_cost,
        li.invoice_month
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily AS li
    LEFT JOIN cte_filtered_tags AS fvl
        ON li.id = fvl.id
    JOIN {{schema | sqlsafe}}.reporting_gcpcostentryproductservice AS ps
        ON li.cost_entry_product_id = ps.id
    JOIN {{schema | sqlsafe}}.reporting_gcpproject AS pj
        ON li.project_id = pj.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_gcpcostentrybill as ab
        ON li.cost_entry_bill_id = ab.id
    WHERE li.usage_start >= {{start_date}}::date
        AND li.usage_start <= {{end_date}}::date
        {% if bill_ids %}
        AND cost_entry_bill_id IN (
            {%- for bill_id in bill_ids  -%}
                {{bill_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%})
        {% endif %}
    GROUP BY li.cost_entry_bill_id,
        pj.account_id,
        pj.project_id,
        pj.project_name,
        ps.service_id,
        ps.service_alias,
        ps.sku_id,
        ps.sku_alias,
        li.usage_start,
        li.usage_end,
        li.line_item_type,
        li.usage_type,
        region,
        li.currency,
        li.usage_pricing_unit,
        fvl.gcp_tags,
        ab.provider_id,
        li.invoice_month
)
;

-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary AS li
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
INSERT INTO {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary (
    uuid,
    cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    usage_start,
    usage_end,
    region,
    instance_type,
    unit,
    tags,
    usage_amount,
    currency,
    line_item_type,
    unblended_cost,
    source_uuid,
    markup_cost,
    invoice_month

)
    SELECT uuid,
    cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    usage_start,
    usage_end,
    region,
    instance_type,
    unit,
    tags,
    usage_amount,
    currency,
    line_item_type,
    unblended_cost,
    source_uuid,
    markup_cost,
    invoice_month
    FROM reporting_gcpcostentrylineitem_daily_summary_{{uuid | sqlsafe}}
;
