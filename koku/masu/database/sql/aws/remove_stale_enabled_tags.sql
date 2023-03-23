-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_awsenabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_awstags_summary AS ts
    WHERE ts.key = etk.key
)
AND etk.enabled = true
;
