INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (
    key,
    values,
    cost_entry_bill_id,
    subscription_guid,
    namespace,
    cluster_id,
    cluster_alias
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_agg(DISTINCT l.subscription_guid) as subscription_guid,
    array_agg(DISTINCT l.namespace),
    max(l.cluster_id) as cluster_id,
    max(l.cluster_alias) as cluster_alias
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.subscription_guid,
        UNNEST(li.namespace) as namespace,
        li.cluster_id,
        li.cluster_alias
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
) l
GROUP BY l.key, l.cost_entry_bill_id, l.namespace, l.cluster_id, l.cluster_alias
ON CONFLICT (key, cost_entry_bill_id, namespace) DO UPDATE
SET values = EXCLUDED.values
;
