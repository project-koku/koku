-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_azuretags_summary AS ts
    WHERE ts.key = etk.key
        AND etk.provider_type = 'Azure'
)
AND etk.enabled = true
AND etk.provider_type = 'Azure'
;
