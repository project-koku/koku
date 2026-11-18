create table {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}} AS
    SELECT key,
        value,
        li.report_period_id,
        li.namespace,
        li.node
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS li,
        jsonb_each_text(li.pod_labels) labels
    WHERE li.data_source = 'Pod'
    {% if report_period_ids %}
        AND li.report_period_id IN {{ report_period_ids | inclause }}
    {% endif %}
        AND li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND value IS NOT NULL
        AND li.pod_labels ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_enabledtagkeys WHERE enabled=true AND provider_type='OCP')
        AND COALESCE(li.infrastructure_project_raw_cost, 0) = 0
        AND COALESCE(li.infrastructure_raw_cost, 0) = 0
    GROUP BY key, value, li.report_period_id, li.namespace, li.node
;

create index ix_cte_tag_value_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}}
       (key, report_period_id, namespace, node)
;


create table {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}} AS
    SELECT tv.key,
        array_agg(DISTINCT value)::text[] as "values",
        report_period_id,
        namespace,
        node
    FROM {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}} tv
    JOIN {{schema | sqlsafe}}.reporting_enabledtagkeys etk
        ON tv.key = etk.key
    WHERE etk.enabled = true
        AND etk.provider_type = 'OCP'
    GROUP BY tv.key, report_period_id, namespace, node
;

create unique index ix_cte_values_agg_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}}
       (key, report_period_id, namespace, node)
;


create table {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} AS
    SELECT v.key,
        array_agg(DISTINCT v."values")::text[] as "values",
        v.report_period_id,
        v.namespace,
        v.node
    FROM (
        SELECT va.key,
            unnest(va."values" || coalesce(ls."values", '{}'::text[]))::text as "values",
            va.report_period_id,
            va.namespace,
            va.node
        FROM {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}} AS va
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ls
            ON va.key = ls.key
                AND va.report_period_id = ls.report_period_id
                AND va.namespace = ls.namespace
                AND va.node = ls.node
    ) as v
    GROUP BY key, report_period_id, namespace, node
;

create unique index ix_cte_distinct_values_agg_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}}
       (key, report_period_id, namespace, node)
;


create table {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}} as
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    array_agg(DISTINCT rp.cluster_id)::text[] as cluster_ids,
    array_agg(DISTINCT rp.cluster_alias)::text[] as cluster_aliases,
    array_agg(DISTINCT tv.namespace)::text[] as namespaces,
    array_agg(DISTINCT tv.node)::text[] as nodes
FROM {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}} AS tv
JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
    ON tv.report_period_id = rp.id
GROUP BY tv.key, tv.value
;

create unique index ix_cte_kv_cluster_agg_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}}
       (key, value)
;


DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ls
WHERE uuid IN (
    SELECT uuid FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary as ls
    WHERE ls.report_period_id IN {{ report_period_ids | inclause }}
    AND EXISTS (
        SELECT 1
        FROM {{schema | sqlsafe}}.reporting_enabledtagkeys AS etk
        WHERE etk.enabled = false
            AND ls.key = etk.key
            AND etk.provider_type = 'OCP'
    )
    ORDER BY ls.uuid
    FOR UPDATE
)
;


UPDATE {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS x
SET values = upd.values
FROM (
    SELECT x.uuid, y.values
    FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS x, {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} AS y
    WHERE y.key = x.key
        AND y.report_period_id = x.report_period_id
        AND y.namespace = x.namespace
        AND y.node = x.node
        AND y.values != x.values
    ORDER BY x.uuid
    FOR UPDATE OF x
) upd
WHERE x.uuid = upd.uuid
;


INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary (uuid, key, report_period_id, namespace, node, values)
SELECT uuid_generate_v4() as uuid,
    key,
    report_period_id,
    namespace,
    node,
    "values"
FROM {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} x
WHERE NOT EXISTS (
          SELECT 1
            FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary y
           WHERE y.key = x.key
             AND y.report_period_id = x.report_period_id
             AND y.namespace = x.namespace
             AND y.node = x.node
      )
ON CONFLICT DO NOTHING
;


UPDATE {{schema | sqlsafe}}.reporting_ocptags_values AS ov
   SET cluster_ids = upd.cluster_ids,
       cluster_aliases = upd.cluster_aliases,
       namespaces = upd.namespaces,
       nodes = upd.nodes
FROM (
    SELECT ov.uuid, ca.cluster_ids, ca.cluster_aliases, ca.namespaces, ca.nodes
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS ov, {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}} AS ca
    WHERE ca.key = ov.key
    AND ca.value = ov.value
    AND (
        ca.cluster_ids != ov.cluster_ids OR
        ca.cluster_aliases != ov.cluster_aliases OR
        ca.namespaces != ov.namespaces OR
        ca.nodes != ov.nodes
    )
    ORDER BY ov.uuid
    FOR UPDATE OF ov
) upd
WHERE ov. uuid = upd.uuid
;


INSERT INTO {{schema | sqlsafe}}.reporting_ocptags_values (uuid, key, value, cluster_ids, cluster_aliases, namespaces, nodes)
SELECT uuid_generate_v4() as uuid,
    tv.key,
    tv.value,
    tv.cluster_ids,
    tv.cluster_aliases,
    tv.namespaces,
    tv.nodes
FROM {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}} AS tv
WHERE not exists (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS rp
    WHERE rp.key = tv.key
        AND rp.value = tv.value
)
ON CONFLICT DO NOTHING
;


TRUNCATE TABLE {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}};
