-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_gcpenabledtagkeys etk
WHERE key IN (
    SELECT key FROM {{schema | sqlsafe}}.reporting_gcpenabledtagkeys etk
    WHERE NOT EXISTS (
        SELECT 1
        FROM {{schema | sqlsafe}}.reporting_gcptags_summary AS ts
        WHERE ts.key = etk.key
    )
    AND etk.enabled = true
    ORDER BY key
    FOR SHARE
)
;
