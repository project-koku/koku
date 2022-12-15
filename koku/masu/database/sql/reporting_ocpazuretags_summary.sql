WITH cte_tag_value AS (
    SELECT key,
        value,
        li.cost_entry_bill_id,
        li.subscription_guid,
        li.report_period_id,
        li.namespace,
        node
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_p AS li,
        jsonb_each_text(li.tags) labels
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
    {% if bill_ids %}
        AND li.cost_entry_bill_id IN (
        {%- for bill_id in bill_ids -%}
        {{bill_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.cost_entry_bill_id, li.subscription_guid, li.report_period_id, li.namespace, li.node
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as "values",
        cost_entry_bill_id,
        report_period_id,
        subscription_guid,
        namespace,
        node
    FROM cte_tag_value
    GROUP BY key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.cost_entry_bill_id,
        v.report_period_id,
        v.subscription_guid,
        v.namespace,
        v.node
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.cost_entry_bill_id,
            va.report_period_id,
            va.subscription_guid,
            va.namespace,
            va.node
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpazuretags_summary AS ls
            ON va.key = ls.key
                AND va.cost_entry_bill_id = ls.cost_entry_bill_id
                AND va.report_period_id = ls.report_period_id
                AND va.subscription_guid = ls.subscription_guid
                AND va.namespace = ls.namespace
                AND va.node = ls.node
    ) as v
    GROUP BY key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpazuretags_summary (uuid, key, values, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node)
    SELECT uuid_generate_v4() as uuid,
        key,
        "values",
        cost_entry_bill_id,
        report_period_id,
        subscription_guid,
        namespace,
        node
    FROM cte_distinct_values_agg
    ON CONFLICT (key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node) DO UPDATE SET values=EXCLUDED."values"
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
