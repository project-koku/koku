WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id,
        li.report_period_id,
        max(li.account_alias_id) as account_alias_id,
        namespace,
        node
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p AS li,
        jsonb_each_text(li.tags) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND li.report_period_id = {{report_period_id}}
        AND li.tags ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_enabledtagkeys WHERE enabled=true AND provider_type='AWS')
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN {{ bill_ids | inclause }}
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id, li.report_period_id, li.namespace, li.node
),
cte_values_agg AS (
    SELECT tv.key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        report_period_id,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        namespace,
        node
    FROM cte_tag_value AS tv
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        ON tv.key = etk.key
    WHERE etk.enabled = true
        AND etk.provider_type = 'AWS'
    GROUP BY tv.key, cost_entry_bill_id, report_period_id, usage_account_id, namespace, node
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.cost_entry_bill_id,
        v.report_period_id,
        v.usage_account_id,
        v.account_alias_id,
        v.namespace,
        v.node
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.cost_entry_bill_id,
            va.report_period_id,
            va.usage_account_id,
            va.account_alias_id,
            va.namespace,
            va.node
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpawstags_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.report_period_id = ls.report_period_id
                AND va.usage_account_id = ls.usage_account_id
                AND va.account_alias_id = ls.account_alias_id
                AND va.namespace = ls.namespace
                AND va.node = ls.node
    ) as v
    GROUP BY key, cost_entry_bill_id, report_period_id, usage_account_id, account_alias_id, namespace, node
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (uuid, key, values, cost_entry_bill_id, report_period_id, usage_account_id, account_alias_id, namespace, node)
    SELECT uuid_generate_v4() as uuid,
        key,
        "values",
        cost_entry_bill_id,
        report_period_id,
        usage_account_id,
        account_alias_id,
        namespace,
        node
    FROM cte_distinct_values_agg
    ON CONFLICT (key, cost_entry_bill_id, report_period_id, usage_account_id, namespace, node) DO UPDATE SET values=EXCLUDED."values"
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_values (uuid, key, value, usage_account_ids, account_aliases, cluster_ids, cluster_aliases, namespaces, nodes)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.usage_account_id) as usage_account_ids,
    array_agg(DISTINCT aa.account_alias) as account_aliases,
    array_agg(DISTINCT rp.cluster_id) as cluster_ids,
    array_agg(DISTINCT rp.cluster_alias) as cluster_aliases,
    array_agg(DISTINCT tv.namespace) as namespaces,
    array_agg(DISTINCT tv.node) as nodes
FROM cte_tag_value AS tv
JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
    ON tv.report_period_id = rp.id
LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON tv.usage_account_id = aa.account_id
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET usage_account_ids=EXCLUDED.usage_account_ids, namespaces=EXCLUDED.namespaces, nodes=EXCLUDED.nodes, cluster_ids=EXCLUDED.cluster_ids, cluster_aliases=EXCLUDED.cluster_aliases
;

DELETE FROM {{schema | sqlsafe}}.reporting_ocpawstags_summary AS ts
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
    FROM {{schema | sqlsafe}}.reporting_ocpawstags_values AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpawstags_summary AS ts
        ON tv.key = ts.key
    WHERE ts.key IS NULL

)
DELETE FROM {{schema | sqlsafe}}.reporting_ocpawstags_values tv
    USING cte_expired_tag_keys etk
    WHERE tv.key = etk.key
;
