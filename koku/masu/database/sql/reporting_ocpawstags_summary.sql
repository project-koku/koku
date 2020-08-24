WITH data(key, value, cost_entry_bill_id, accounts, namespace, cluster_id, cluster_alias) AS (
    SELECT l.key,
        l.value,
        l.cost_entry_bill_id,
        array_cat(array_agg(DISTINCT l.usage_account_id), array_agg(DISTINCT aa.account_alias )) AS accounts,
        array_agg(DISTINCT l.namespace),
        max(l.cluster_id) AS cluster_id,
        max(l.cluster_alias) AS cluster_alias
    FROM (
        SELECT key,
            value,
            li.cost_entry_bill_id,
            li.usage_account_id,
            UNNEST(li.namespace) AS namespace,
            li.cluster_id,
            li.cluster_alias
        FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary AS li,
            jsonb_each_text(li.tags) labels
    ) l
    LEFT JOIN {{schema | sqlsafe}}.reporting_awsaccountalias AS aa
            ON l.usage_account_id = aa.account_id
    GROUP BY l.key, l.value, l.cost_entry_bill_id, l.namespace, l.cluster_id, l.cluster_alias
),
data2(key, values, namespace) AS (SELECT data.key, array_agg(DISTINCT data.value), namespace from data GROUP BY data.key, data.namespace)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (key, cost_entry_bill_id, accounts, namespace, cluster_id, cluster_alias, values)
    SELECT DISTINCT data.key AS key,
    data.cost_entry_bill_id AS cost_entry_bill_id,
    data.accounts AS accounts,
    data.namespace AS namespace,
    data.cluster_id AS cluster_id,
    data.cluster_alias AS cluster_alias,
    data2.values AS values
    FROM data INNER JOIN data2 ON data.key = data2.key AND data.namespace = data2.namespace
    ON CONFLICT (key, cost_entry_bill_id, namespace) DO UPDATE SET key = EXCLUDED.key
    RETURNING key, id as key_id
    )
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_values (value)
   SELECT DISTINCT d.value
   FROM data d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary_values_mtm (ocpawstagssummary_id, ocpawstagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM data d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (ocpawstagssummary_id, ocpawstagsvalues_id) DO NOTHING
;
