
WITH data(key, value, cost_id, subscription_guid) AS (
    SELECT l.key,
        l.value,
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
    GROUP BY l.key, l.value, l.cost_entry_bill_id
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary (key, cost_entry_bill_id, subscription_guid)
    SELECT DISTINCT key, cost_id, subscription_guid
    FROM data
    ON CONFLICT (key, cost_entry_bill_id) DO UPDATE SET key=EXCLUDED.key
    RETURNING key, id as key_id
)
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_values (value)
   SELECT DISTINCT d.value
   FROM data d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
   )

INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary_values (azuretagssummary_id, azuretagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM data d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (azuretagssummary_id, azuretagsvalues_id) DO NOTHING;
