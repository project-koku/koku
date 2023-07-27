WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.account_id,
        li.project_id,
        li.project_name
    FROM {{schema | sqlsafe}}.reporting_gcpcostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND value IS NOT NULL
        AND li.tags ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_enabledtagkeys WHERE enabled=true AND provider_type='GCP')
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN {{ bill_ids | inclause }}
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.account_id, li.project_id, li.project_name
),
cte_values_agg AS (
    SELECT tv.key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name
    FROM cte_tag_value AS tv
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON tv.key = etk.key
    WHERE etk.enabled = true
        AND etk.provider_type = 'GCP'
    GROUP BY tv.key, cost_entry_bill_id, account_id, project_id, project_name
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.cost_entry_bill_id,
        v.account_id,
        v.project_id,
        v.project_name
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.cost_entry_bill_id,
            va.account_id,
            va.project_id,
            va.project_name
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_gcptags_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.account_id = ls.account_id
                AND va.project_id = ls.project_id
                AND va.project_name = ls.project_name
    ) as v
    GROUP BY key, cost_entry_bill_id, account_id, project_id, project_name
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_gcptags_summary (uuid, key, cost_entry_bill_id, account_id, project_id, project_name, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name,
        "values"
    FROM cte_distinct_values_agg
    ON CONFLICT (key, cost_entry_bill_id, account_id, project_id, project_name) DO UPDATE SET values=EXCLUDED."values"
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

DELETE FROM {{schema | sqlsafe}}.reporting_gcptags_summary AS ts
WHERE EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
    WHERE etk.enabled = false
        AND etk.provider_type = 'GCP'
        AND ts.key = etk.key
)
;

WITH cte_expired_tag_keys AS (
    SELECT DISTINCT tv.key
    FROM {{schema | sqlsafe}}.reporting_gcptags_values AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_gcptags_summary AS ts
        ON tv.key = ts.key
    WHERE ts.key IS NULL

)
DELETE FROM {{schema | sqlsafe}}.reporting_gcptags_values tv
    USING cte_expired_tag_keys etk
    WHERE tv.key = etk.key
;
