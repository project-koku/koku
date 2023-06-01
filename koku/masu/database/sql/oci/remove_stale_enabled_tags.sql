-- Delete stale enabled keys
DELETE FROM {{schema_name | sqlsafe}}.reporting_ocienabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema_name | sqlsafe}}.reporting_ocitags_summary AS ts
    WHERE ts.key = etk.key
)
AND etk.enabled = true
;
