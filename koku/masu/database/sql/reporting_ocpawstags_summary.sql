WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.usage_account_id,
        max(li.account_alias_id) as account_alias_id,
        project as namespace,
        max(li.cluster_id) as cluster_id,
        max(li.cluster_alias) as cluster_alias
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary AS li,
        jsonb_each_text(li.tags) labels,
        unnest(li.namespace) projects(project)
    GROUP BY key, value, li.cost_entry_bill_id, li.usage_account_id, project
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        cost_entry_bill_id,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        namespace
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, usage_account_id, namespace
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary (key, cost_entry_bill_id, usage_account_id, account_alias_id, namespace, cluster_id, cluster_alias, values)
    SELECT key,
        cost_entry_bill_id,
        usage_account_id,
        account_alias_id,
        namespace,
        cluster_id,
        cluster_alias,
        values
    FROM cte_values_agg
    ON CONFLICT (key, cost_entry_bill_id, usage_account_id, namespace) DO UPDATE SET key = EXCLUDED.key
    RETURNING key, id as key_id
    )
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_values (value)
   SELECT DISTINCT d.value
   FROM cte_tag_value d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawstags_summary_values_mtm (ocpawstagssummary_id, ocpawstagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM cte_tag_value d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (ocpawstagssummary_id, ocpawstagsvalues_id) DO NOTHING
;
