WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id,
        li.report_period_id,
        max(li.account_alias_id) as account_alias_id,
        project as namespace,
        node
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels,
        unnest(li.namespace) projects(project)
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id, li.report_period_id, project, li.node
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        report_period_id,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        namespace,
        node
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, report_period_id, usage_account_id, namespace, node
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (uuid, key, values, cost_entry_bill_id, report_period_id, usage_account_id, account_alias_id, namespace, node)
    SELECT uuid_generate_v4() as uuid,
        key,
        values,
        cost_entry_bill_id,
        report_period_id,
        usage_account_id,
        account_alias_id,
        namespace,
        node
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, report_period_id, usage_account_id, namespace, node) DO UPDATE SET values=EXCLUDED.values
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
