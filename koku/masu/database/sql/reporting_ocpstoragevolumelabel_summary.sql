WITH DATA(key, value, report_period_id, namespace) AS (
    SELECT l.key,
        l.value,
        l.report_period_id,
        array_agg(DISTINCT l.namespace)
    FROM (
        SELECT key,
            value,
            li.report_period_id,
            li.namespace
        FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li,
            jsonb_each_text(li.persistentvolume_labels || li.persistentvolumeclaim_labels) labels
        {% if report_periods %}
        WHERE li.report_period_id IN (
            {%- for report_period_id in report_period_ids -%}
            {{report_period_id}}{% if not loop.last %},{% endif %}
            {%- endfor -%}
        )
        {% endif %}
    ) l
    GROUP BY l.key, l.value, l.report_period_id, l.namespace
),
data2(key, values, namespace) AS (SELECT data.key, array_agg(DISTINCT data.value), namespace from data GROUP BY data.key, data.namespace)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (key, report_period_id, namespace, values)
    SELECT DISTINCT data.key as key,
    data.report_period_id as report_period_id,
    data.namespace as namespace,
    data2.values as values
    FROM data INNER JOIN data2 ON data.key = data2.key AND data.namespace = data2.namespace
    ON CONFLICT (key, report_period_id, namespace) DO UPDATE SET key = EXCLUDED.key
    RETURNING key, id as key_id
    )
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_ocptags_values (value)
   SELECT DISTINCT d.value
   FROM data d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary_values_mtm (ocpstoragevolumelabelsummary_id, ocptagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM data d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (ocpstoragevolumelabelsummary_id, ocptagsvalues_id) DO NOTHING
;
