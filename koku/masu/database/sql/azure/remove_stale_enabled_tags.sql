-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_azureenabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts
    WHERE ts.key = etk.key
)
AND etk.enabled = true
;
