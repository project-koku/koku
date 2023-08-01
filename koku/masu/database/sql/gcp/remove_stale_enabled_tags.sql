-- Delete stale enabled keys
DELETE FROM {{schema | sqlsafe}}.reporting_enabledtagkeys etk
WHERE NOT EXISTS (
    SELECT 1
    FROM {{schema | sqlsafe}}.reporting_gcptags_summary AS ts
    WHERE ts.key = etk.key
        AND etk.provider_type = 'GCP'
)
AND etk.enabled = true
and etk.provider_type = 'GCP'
;
