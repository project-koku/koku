create table {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}} as
    SELECT key,
        value,
        li.report_period_id,
        li.namespace,
        li.node
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS li,
        jsonb_each_text(li.volume_labels) labels
    WHERE li.data_source = 'Storage'
    {% if report_period_ids %}
        AND li.report_period_id IN (
        {%- for report_period_id in report_period_ids -%}
        {{report_period_id}}{% if not loop.last %},{% endif %}
        {%- endfor -%}
    )
    {% endif %}
        AND li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
        AND value IS NOT NULL
        AND li.volume_labels ?| (SELECT array_agg(DISTINCT key) FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys WHERE enabled=true)
    GROUP BY key, value, li.report_period_id, li.namespace, li.node
;

create index ix_cte_tag_value_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}}
       (key, report_period_id, namespace, node)
;


create table {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}} as
    SELECT tv.key,
        array_agg(DISTINCT value)::text[] as "values",
        report_period_id,
        namespace,
        node
    FROM {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}} tv
    JOIN {{schema | sqlsafe}}.reporting_ocpenabledtagkeys etk
        ON tv.key = etk.key
    WHERE etk.enabled = true
    GROUP BY tv.key, report_period_id, namespace, node
;

create unique index ix_cte_values_agg_{{uuid | sqlsafe}}
    on {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}}
       (key, report_period_id, namespace, node)
;


create table {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} as
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
        LEFT JOIN {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ls
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


UPDATE {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary x
   SET "values" = y."values"
  FROM {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} y
 WHERE y.key = x.key
   AND y.report_period_id = x.report_period_id
   AND y.namespace = x.namespace
   AND y.node = x.node
   AND y.values != x.values
;


INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (uuid, key, report_period_id, namespace, node, values)
SELECT uuid_generate_v4() as uuid,
    key,
    report_period_id,
    namespace,
    node,
    "values"
FROM {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}} x
WHERE NOT EXISTS (
          SELECT 1
            FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary y
           WHERE y.key = x.key
             AND y.report_period_id = x.report_period_id
             AND y.namespace = x.namespace
             AND y.node = x.node
      )
;


UPDATE {{schema | sqlsafe}}.reporting_ocptags_values ov
   SET cluster_ids = ca.cluster_ids,
       cluster_aliases = ca.cluster_aliases,
       namespaces = ca.namespaces,
       nodes = ca.nodes
  FROM {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}} ca
 WHERE ca.key = ov.key
   AND ca.value = ov.value
   AND (
         ca.cluster_ids != ov.cluster_ids OR
         ca.cluster_aliases != ov.cluster_aliases OR
         ca.namespaces != ov.namespaces OR
         ca.nodes != ov.nodes
       )
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


-- We run this SQL in the volume label summary SQL as it is run after
-- the pod summary SQL and we want to make sure we consider both
-- source tables before deleting from the values table.
-- WITH cte_expired_tag_keys AS (
--     SELECT DISTINCT tv.key
--     FROM {{schema | sqlsafe}}.reporting_ocptags_values AS tv
--     LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS pls
--         ON tv.key = pls.key
--     LEFT JOIN {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary vls
--         ON tv.key = vls.key
--     WHERE pls.key IS NULL
--         AND vls.key IS NULL


-- )
DELETE FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS ls
WHERE EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys AS etk
    WHERE etk.enabled = false
        AND ls.key = etk.key
)
;


DELETE FROM {{schema | sqlsafe}}.reporting_ocptags_values tv
WHERE EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys AS etk
    WHERE etk.enabled = false
        AND tv.key = etk.key
)
;

TRUNCATE TABLE {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_tag_value_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_values_agg_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_distinct_values_agg_{{uuid | sqlsafe}};
TRUNCATE TABLE {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.cte_kv_cluster_agg_{{uuid | sqlsafe}};
