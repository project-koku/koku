
WITH cte_tag_value AS (
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
    GROUP BY key, value, li.cost_entry_bill_id, li.subscription_guid
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        subscription_guid
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, subscription_guid
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary (key, cost_entry_bill_id, subscription_guid, values)
    SELECT key,
        cost_entry_bill_id,
        subscription_guid,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, subscription_guid) DO UPDATE SET values=EXCLUDED.values
    RETURNING key, id as key_id
)
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_values (value)
   SELECT DISTINCT d.value
   FROM cte_tag_value d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
   )

INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary_values_mtm (azuretagssummary_id, azuretagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM cte_tag_value d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (azuretagssummary_id, azuretagsvalues_id) DO NOTHING;
