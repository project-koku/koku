WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_tag_value AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    GROUP BY key, cost_entry_bill_id, usage_account_id, aa.id
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary (uuid, key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, usage_account_id) DO UPDATE SET values=EXCLUDED.values
)
INSERT INTO {{schema | sqlsafe}}.reporting_awstags_values (uuid, key, value, usage_account_ids, account_aliases)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.usage_account_id) as usage_account_ids,
    array_agg(DISTINCT aa.account_alias) as account_aliases
FROM cte_tag_value AS tv
LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON tv.usage_account_id = aa.account_id
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET usage_account_ids=EXCLUDED.usage_account_ids
;
