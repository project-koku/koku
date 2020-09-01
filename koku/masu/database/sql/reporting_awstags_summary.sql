WITH cte_tag_value AS (
    SELECT
        key,
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
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_tag_value AS tv
    JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON tv.usage_account_id = aa.account_id
    GROUP BY key, cost_entry_bill_id, usage_account_id, aa.id
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary (key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
    SELECT key,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, usage_account_id) DO UPDATE SET key=EXCLUDED.key
    RETURNING key, id as key_id
)
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_awstags_values (value)
   SELECT DISTINCT d.value
   FROM cte_tag_value d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
   )

INSERT INTO {{schema | sqlsafe}}.reporting_awstags_summary_values_mtm (awstagssummary_id, awstagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM cte_tag_value d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (awstagssummary_id, awstagsvalues_id) DO NOTHING;
