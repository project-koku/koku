-- Delete stale enabled keys
DELETE FROM {{schema_name | sqlsafe}}.reporting_gcpenabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema_name | sqlsafe}}.reporting_gcptags_summary AS ts
    WHERE ts.key = etk.key
)
AND etk.enabled = true
;
