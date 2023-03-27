-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_ocienabledtagkeys etk
WHERE key IN (
    SELECT key FROM {{schema | sqlsafe}}.reporting_ocienabledtagkeys etk
    WHERE NOT EXISTS (
        SELECT 1
        FROM {{schema | sqlsafe}}.reporting_ocitags_summary AS ts
        WHERE ts.key = etk.key
    )
    AND etk.enabled = true
    ORDER BY key
    FOR SHARE
)
;
