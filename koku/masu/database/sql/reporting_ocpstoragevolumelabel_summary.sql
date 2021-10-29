WITH cte_tag_value(key, value, report_period_id, namespace) AS (
    SELECT key,
        value,
        li.report_period_id,
        li.namespace,
        li.node
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS li,
        jsonb_each_text(li.volume_labels) labels
    WHERE li.data_source = 'Storage'
    {% if report_periods %}
        AND li.report_period_id IN (
        {%- for report_period_id in report_period_ids -%}
        {{report_period_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
        AND li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
    GROUP BY key, value, li.report_period_id, li.namespace, li.node
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as "values",
        report_period_id,
        namespace,
        node
    FROM cte_tag_value
    GROUP BY key, report_period_id, namespace, node
),
cte_distinct_values_agg AS (
    SELECT v.key,
        array_agg(DISTINCT v."values") as "values",
        v.report_period_id,
        v.namespace,
        v.node
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[])) as "values",
            va.report_period_id,
            va.namespace,
            va.node
        FROM cte_values_agg AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ls
            ON va.key = ls.key
                AND va.report_period_id = ls.report_period_id
                AND va.namespace = ls.namespace
                AND va.node = ls.node
    ) as v
    GROUP BY key, report_period_id, namespace, node
),
ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (uuid, key, report_period_id, namespace, node, values)
    SELECT uuid_generate_v4() as uuid,
        key,
        report_period_id,
        namespace,
        node,
        "values"
    FROM cte_distinct_values_agg
    ON CONFLICT (key, report_period_id, namespace, node) DO UPDATE SET values=EXCLUDED."values"
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

-- We run this SQL in the volume label summary SQL as it is run after
-- the pod summary SQL and we want to make sure we consider both
-- source tables before deleting from the values table.
WITH cte_expired_tag_keys AS (
    SELECT DISTINCT tv.key
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS tv
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS pls
        ON tv.key = pls.key
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary vls
        ON tv.key = vls.key
    WHERE pls.key IS NULL
        AND vls.key IS NULL


)
DELETE FROM {{schema | sqlsafe}}.reporting_ocptags_values tv
    USING cte_expired_tag_keys etk
    WHERE tv.key = etk.key
;
