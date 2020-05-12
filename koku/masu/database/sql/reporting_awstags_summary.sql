INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary (
    key,
    values,
    cost_entry_bill_id,
    accounts
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_cat(array_agg(DISTINCT l.usage_account_id), array_agg(DISTINCT aa.account_alias )) as accounts
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
) l
LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON l.usage_account_id = aa.account_id
GROUP BY l.key, l.cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
