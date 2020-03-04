INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (
    key,
    values,
    cost_entry_bill_id,
    subscription_guid,
    namespace
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_agg(DISTINCT l.subscription_guid) as subscription_guid,
    array_agg(DISTINCT l.namespace) as namespace
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.subscription_guid,
        UNNEST(li.namespace) as namespace
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
) l
GROUP BY l.key, l.cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
