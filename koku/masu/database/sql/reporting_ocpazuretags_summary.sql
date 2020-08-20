WITH DATA(key, value, cost_entry_bill_id, subscription_guid, namespace, cluster_id, cluster_alias) AS (
    SELECT l.key,
        l.value,
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
    GROUP BY l.key, l.value, l.cost_entry_bill_id, l.namespace, l.cluster_id, l.cluster_alias
),
data2(key, values) AS (SELECT data.key, array_agg(DISTINCT data.value) from data GROUP BY data.key)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (key, cost_entry_bill_id, subscription_guid, namespace, cluster_id, cluster_alias, values)
    SELECT DISTINCT data.key as key,
    data.cost_entry_bill_id as cost_entry_bill_id,
    data.subscription_guid as subscription_guid,
    data.namespace as namespace,
    data.cluster_id as cluster_id,
    data.cluster_alias as cluster_alias,
    data2.values as values
    FROM data INNER JOIN data2 ON data.key = data2.key
    ON CONFLICT (key, cost_entry_bill_id, namespace) DO UPDATE SET key = EXCLUDED.key
    RETURNING key, id as key_id
    )
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_values (value)
   SELECT DISTINCT d.value
   FROM data d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary_values_mtm (ocpazuretagssummary_id, ocpazuretagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM data d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (ocpazuretagssummary_id, ocpazuretagsvalues_id) DO NOTHING
;
