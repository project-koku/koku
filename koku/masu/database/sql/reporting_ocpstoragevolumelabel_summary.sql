WITH cte_tag_value(key, value, report_period_id, namespace) AS (
    SELECT key,
        value,
        li.report_period_id,
        li.namespace,
        li.node
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li,
        jsonb_each_text(li.persistentvolume_labels || li.persistentvolumeclaim_labels) labels
    {% if report_periods %}
    WHERE li.report_period_id IN (
        {%- for report_period_id in report_period_ids -%}
        {{report_period_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
    GROUP BY key, value, li.report_period_id, li.namespace, li.node
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        report_period_id,
        namespace,
        node
    FROM cte_tag_value
    GROUP BY key, report_period_id, namespace, node
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (uuid, key, report_period_id, namespace, node, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        report_period_id,
        namespace,
        node,
        values
    FROM cte_values_agg
    ON CONFLICT (key, report_period_id, namespace) DO UPDATE SET values=EXCLUDED.values
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocptags_values (uuid, key, value, cluster_ids, cluster_aliases, namespaces, nodes)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT rp.cluster_id) as cluster_ids,
    array_agg(DISTINCT rp.cluster_alias) as cluster_aliases,
    array_agg(DISTINCT tv.namespace) as namespaces,
    array_agg(DISTINCT tv.node) as nodes
FROM cte_tag_value AS tv
JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
    ON tv.report_period_id = rp.id
GROUP BY tv.key, tv.value
ON CONFLICT (key, value) DO UPDATE SET namespaces=EXCLUDED.namespaces, nodes=EXCLUDED.nodes, cluster_ids=EXCLUDED.cluster_ids, cluster_aliases=EXCLUDED.cluster_aliases
;
