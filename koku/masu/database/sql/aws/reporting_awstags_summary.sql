WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND li.tags ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_enabledtagkeys WHERE enabled=true AND provider_type='AWS')
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN {{ bill_ids | inclause }}
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id
),
cte_values_agg AS (
    SELECT tv.key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_tag_value AS tv
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON tv.key = etk.key
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    WHERE etk.enabled = true
        AND etk.provider_type = 'AWS'
    GROUP BY tv.key, cost_entry_bill_id, usage_account_id, aa.id
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.cost_entry_bill_id,
        v.usage_account_id,
        v.account_alias_id
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.cost_entry_bill_id,
            va.usage_account_id,
            va.account_alias_id
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_awstags_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.usage_account_id = ls.usage_account_id
                AND va.account_alias_id = ls.account_alias_id
    ) as v
    GROUP BY key, cost_entry_bill_id, usage_account_id, account_alias_id
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary (uuid, key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        "values"
    FROM cte_distinct_values_agg
    ON CONFLICT (key, cost_entry_bill_id, usage_account_id) DO UPDATE SET values=EXCLUDED."values"
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

DELETE FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts
WHERE EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
    WHERE etk.enabled = false
        AND etk.provider_type = 'AWS'
        AND ts.key = etk.key
)
;

WITH cte_expired_tag_keys AS (
    SELECT DISTINCT tv.key
    FROM {{schema | sqlsafe}}.reporting_awstags_values AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_awstags_summary AS ts
        ON tv.key = ts.key
    WHERE ts.key IS NULL

)
DELETE FROM {{schema | sqlsafe}}.reporting_awstags_values tv
    USING cte_expired_tag_keys etk
    WHERE tv.key = etk.key
;
