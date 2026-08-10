-- Delete reporting_ocptags_values rows whose (key, value) no longer appear
-- in pod or volume label summaries. Materialize live pairs once via UNNEST,
-- then anti-join (avoids correlated ANY() probes per tag-values row).
WITH live_tag_values AS (
    SELECT DISTINCT key, value
    FROM (
        SELECT ps.key, unnest(ps.values) AS value
        FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS ps
        UNION ALL
        SELECT vs.key, unnest(vs.values) AS value
        FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS vs
    ) AS kv
),
orphans AS (
    SELECT tv.uuid
    FROM {{schema | sqlsafe}}.reporting_ocptags_values AS tv
    LEFT JOIN live_tag_values AS live
        ON live.key = tv.key
       AND live.value = tv.value
    WHERE live.key IS NULL
)
DELETE FROM {{schema | sqlsafe}}.reporting_ocptags_values AS tv
    USING orphans AS o
    WHERE tv.uuid = o.uuid
;
