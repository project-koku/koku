WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.account_id,
        li.project_id,
        li.project_name
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    {% if bill_ids %}
    WHERE li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.account_id, li.project_id, li.project_name
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, account_id, project_id, project_name
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_gcptags_summary (uuid, key, cost_entry_bill_id, account_id, project_id, project_name, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, account_id, project_id) DO UPDATE SET values=EXCLUDED.values
)
INSERT INTO {{schema | sqlsafe}}.reporting_gcptags_values (uuid, key, value, account_ids, project_ids, project_names)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.account_id) as account_ids,
    array_agg(DISTINCT tv.project_id) as project_ids,
    array_agg(DISTINCT tv.project_name) as project_names
FROM cte_tag_value AS tv
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET account_ids=EXCLUDED.account_ids, project_ids=EXCLUDED.project_ids, project_names=EXCLUDED.project_names
;
