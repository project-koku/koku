INSERT INTO {{schema | sqlsafe }}.reporting_azuretags_summary (
    key,
    values,
    cost_entry_bill_id
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id
    FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily AS li,
        jsonb_each_text(li.tags) labels
) l
GROUP BY l.key, l.cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
