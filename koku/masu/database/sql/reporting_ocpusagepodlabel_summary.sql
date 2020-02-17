INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary (
    key,
    values,
    report_period_id,
    namespace
)
SELECT l.key,
    array_agg(DISTINCT l.value) as values,
    l.report_period_id,
    array_agg(DISTINCT l.namespace) as namespace
FROM (
    SELECT key,
        value,
        li.report_period_id,
        li.namespace
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily AS li,
        jsonb_each_text(li.pod_labels) labels
) l
GROUP BY l.key, l.report_period_id, l.namespace
ON CONFLICT (key, report_period_id) DO UPDATE
SET values = EXCLUDED.values
;
