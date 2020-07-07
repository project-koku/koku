INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (
    key,
    values,
    cost_entry_bill_id,
    accounts,
    namespace,
    cluster_id
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_cat(array_agg(DISTINCT l.usage_account_id), array_agg(DISTINCT aa.account_alias )) as accounts,
    array_agg(DISTINCT l.namespace),
    max(l.cluster_id) as cluster_id
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id,
        UNNEST(li.namespace) as namespace,
        li.cluster_id
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
) l
LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
        ON l.usage_account_id = aa.account_id
GROUP BY l.key, l.cost_entry_bill_id, l.namespace, l.cluster_id
ON CONFLICT (key, cost_entry_bill_id, namespace) DO UPDATE
SET values = EXCLUDED.values
;
