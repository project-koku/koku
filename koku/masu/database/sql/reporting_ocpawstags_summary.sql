INSERT INTO acct10001.reporting_ocpawstags_summary (
    key,
    values,
    cost_entry_bill_id,
    accounts,
    namespace
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.cost_entry_bill_id,
    array_cat(array_agg(DISTINCT l.usage_account_id), array_agg(DISTINCT aa.account_alias )) as accounts,
    array_agg(DISTINCT l.namespace) as namespace
FROM (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id,
        li.namespace
    FROM acct10001.reporting_ocpawscostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels
) l
LEFT JOIN acct10001.reporting_awsaccountalias AS aa
        ON l.usage_account_id = aa.account_id
GROUP BY l.key, l.cost_entry_bill_id
ON CONFLICT (key, cost_entry_bill_id) DO UPDATE
SET values = EXCLUDED.values
;
