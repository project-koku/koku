
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
),
data2(key, values) AS (SELECT data.key, array_agg(DISTINCT data.value) from data GROUP BY data.key)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary (key, cost_entry_bill_id, subscription_guid, values)
    SELECT DISTINCT data.key as key,
    data.cost_id as cost_entry_bill_id,
    data.subscription_guid as subscription_guid,
    data2.values as values
    FROM data INNER JOIN data2 ON data.key = data2.key
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

INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary_values_mtm (azuretagssummary_id, azuretagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM data d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (azuretagssummary_id, azuretagsvalues_id) DO NOTHING;
