WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.subscription_guid,
        li.report_period_id,
        project as namespace,
        node
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels,
        unnest(li.namespace) projects(project)
    GROUP BY key, value, li.cost_entry_bill_id, li.subscription_guid, li.report_period_id, project, li.node
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        report_period_id,
        subscription_guid,
        namespace,
        node
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (uuid, key, values, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node)
    SELECT uuid_generate_v4() as uuid,
        key,
        values,
        cost_entry_bill_id,
        report_period_id,
        subscription_guid,
        namespace,
        node
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node) DO UPDATE SET values=EXCLUDED.values
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_values (uuid, key, value, subscription_guids, cluster_ids, cluster_aliases, namespaces, nodes)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT tv.subscription_guid) as subscription_guids,
    array_agg(DISTINCT rp.cluster_id) as cluster_ids,
    array_agg(DISTINCT rp.cluster_alias) as cluster_aliases,
    array_agg(DISTINCT tv.namespace) as namespaces,
    array_agg(DISTINCT tv.node) as nodes
FROM cte_tag_value AS tv
JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
    ON tv.report_period_id = rp.id
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET subscription_guids=EXCLUDED.subscription_guids, namespaces=EXCLUDED.namespaces, nodes=EXCLUDED.nodes, cluster_ids=EXCLUDED.cluster_ids, cluster_aliases=EXCLUDED.cluster_aliases
;
