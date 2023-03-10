WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.payer_tenant_id
    FROM {{schema | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND li.tags ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_ocienabledtagkeys WHERE enabled=true)
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.payer_tenant_id
),
cte_values_agg AS (
    SELECT tv.key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        payer_tenant_id
    FROM cte_tag_value AS tv
    JOIN {{schema | sqlsafe}}.reporting_ocienabledtagkeys etk
        ON tv.key = etk.key
    WHERE etk.enabled = true
    GROUP BY tv.key, cost_entry_bill_id, payer_tenant_id
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.cost_entry_bill_id,
        v.payer_tenant_id
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.cost_entry_bill_id,
            va.payer_tenant_id
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocitags_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.payer_tenant_id = ls.payer_tenant_id
    ) as v
    GROUP BY key, cost_entry_bill_id, payer_tenant_id
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocitags_summary (uuid, key, cost_entry_bill_id, payer_tenant_id, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        cost_entry_bill_id,
        payer_tenant_id,
        "values"
    FROM cte_distinct_values_agg
    ON CONFLICT (key, cost_entry_bill_id, payer_tenant_id) DO UPDATE SET values=EXCLUDED."values"
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocitags_values (uuid, key, value, payer_tenant_ids)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.payer_tenant_id) as payer_tenant_ids
FROM cte_tag_value AS tv
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET payer_tenant_ids=EXCLUDED.payer_tenant_ids
;

DELETE FROM {{schema | sqlsafe}}.reporting_ocitags_summary AS ts
WHERE EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocienabledtagkeys AS etk
    WHERE etk.enabled = false
        AND ts.key = etk.key
)
;

WITH cte_expired_tag_keys AS (
    SELECT DISTINCT tv.key
    FROM {{schema | sqlsafe}}.reporting_ocitags_values AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocitags_summary AS ts
        ON tv.key = ts.key
    WHERE ts.key IS NULL

)
DELETE FROM {{schema | sqlsafe}}.reporting_ocitags_values tv
    USING cte_expired_tag_keys etk
    WHERE tv.key = etk.key
;
