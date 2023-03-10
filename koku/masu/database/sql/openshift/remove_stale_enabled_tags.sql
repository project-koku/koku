-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary AS pls
    WHERE pls.key = etk.key
)
AND NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocpstoragevolumelabel_summary AS vls
    WHERE vls.key = etk.key
)
AND etk.enabled = true
;
