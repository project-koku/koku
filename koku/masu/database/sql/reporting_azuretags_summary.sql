INSERT INTO {{schema | sqlsafe}}.reporting_azuretags_summary
SELECT l.key,
    array_agg(DISTINCT l.value) as values
FROM (
    SELECT key,
        value
    FROM {{schema | sqlsafe}.reporting_azurecostentrylineitem_daily AS li,
        jsonb_each_text(li.tags) labels
) l
GROUP BY l.key
ON CONFLICT (key) DO UPDATE
SET values = EXCLUDED.values
;
