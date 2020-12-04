WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.account_id
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.account_id
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        tv.account_id
    FROM cte_tag_value AS tv
    GROUP BY key, cost_entry_bill_id, tv.account_id
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_gcptags_summary (uuid, key, cost_entry_bill_id, account_id, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        account_id,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, account_id) DO UPDATE SET values=EXCLUDED.values
)
INSERT INTO {{schema | sqlsafe}}.reporting_gcptags_values (uuid, key, value, account_ids)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.account_id) as account_ids
FROM cte_tag_value AS tv
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET account_ids=EXCLUDED.account_ids
;
