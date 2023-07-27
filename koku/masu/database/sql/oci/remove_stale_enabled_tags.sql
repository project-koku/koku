-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_ocitags_summary AS ts
    WHERE ts.key = etk.key
    AND etk.provider_type = 'OCI'
)
AND etk.enabled = true
AND etk.provider_type = 'OCI'
;
