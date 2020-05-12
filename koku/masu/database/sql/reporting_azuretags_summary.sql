INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary (
    key,
    values,
    cost_entry_bill_id,
    subscription_guid
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_agg(DISTINCT l.subscription_guid) as subscription_guid
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.subscription_guid
    FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
) l
GROUP BY l.key, l.cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
