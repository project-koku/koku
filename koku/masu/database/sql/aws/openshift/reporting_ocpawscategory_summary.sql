-- Delete disabled keys
WITH cte_disabled_category_keys AS (
    SELECT DISTINCT key FROM {{schema | sqlsafe}}.reporting_awsenabledcategorykeys WHERE enabled=False
)
DELETE FROM {{schema | sqlsafe}}.reporting_ocpawscategory_summary acs
    USING cte_disabled_category_keys dis
    WHERE acs.key = dis.key
;

WITH cte_category_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p AS li,
        jsonb_each_text(li.aws_cost_category) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND li.aws_cost_category ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_awsenabledcategorykeys WHERE enabled=true)
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN {{ bill_ids | inclause }}
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id
),
cte_values_agg AS (
    SELECT cat_vals.key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        usage_account_id,
        aa.id as account_alias_id
    FROM cte_category_value AS cat_vals
    JOIN {{schema | sqlsafe}}.reporting_awsenabledcategorykeys AS eck
        ON cat_vals.key = eck.key
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON cat_vals.usage_account_id = aa.account_id
    WHERE eck.enabled = true
    GROUP BY cat_vals.key, cost_entry_bill_id, usage_account_id, aa.id
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
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpawscategory_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.usage_account_id = ls.usage_account_id
                AND va.account_alias_id = ls.account_alias_id
    ) as v
    GROUP BY key, cost_entry_bill_id, usage_account_id, account_alias_id
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawscategory_summary (uuid, key, cost_entry_bill_id, usage_account_id, account_alias_id, values)
SELECT uuid_generate_v4() as uuid,
    key,
    cost_entry_bill_id,
    usage_account_id,
    account_alias_id,
    "values"
FROM cte_distinct_values_agg
ON CONFLICT (key, cost_entry_bill_id, usage_account_id) DO UPDATE SET values=EXCLUDED."values";
