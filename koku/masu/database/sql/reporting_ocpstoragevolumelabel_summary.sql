WITH cte_tag_value(key, value, report_period_id, namespace) AS (
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
    GROUP BY key, value, li.report_period_id, li.namespace
),
cte_values_agg AS (
    SELECT key,
        array_agg(DISTINCT value) as values,
        report_period_id,
        namespace
    FROM cte_tag_value
    GROUP BY key, report_period_id, namespace
)
, ins1 AS (
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary (key, report_period_id, namespace, values)
    SELECT key,
    report_period_id,
    namespace,
    values
    FROM cte_values_agg
    ON CONFLICT (key, report_period_id, namespace) DO UPDATE SET values=EXCLUDED.values
    RETURNING key, id AS key_id
    )
, ins2 AS (
   INSERT INTO {{schema | sqlsafe}}.reporting_ocptags_values (value)
   SELECT DISTINCT d.value
   FROM cte_tag_value d
   ON CONFLICT (value) DO UPDATE SET value=EXCLUDED.value
   RETURNING value, id AS values_id
    )
INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary_values_mtm (ocpstoragevolumelabelsummary_id, ocptagsvalues_id)
SELECT DISTINCT ins1.key_id, ins2.values_id
FROM cte_tag_value d
INNER JOIN ins1 ON d.key = ins1.key
INNER JOIN ins2 ON d.value = ins2.value
ON CONFLICT (ocpstoragevolumelabelsummary_id, ocptagsvalues_id) DO NOTHING
;
