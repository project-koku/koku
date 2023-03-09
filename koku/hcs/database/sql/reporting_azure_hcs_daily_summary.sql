SELECT
*,
'{{ebs_acct_num | sqlsafe}}' AS ebs_account_id,
'{{org_id | sqlsafe}}' AS org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE source = '{{provider_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND publishertype = 'Marketplace'
    AND (publishername LIKE '%Red Hat%'
        OR (publishername = 'Microsoft' AND (
           metersubcategory LIKE '%Red Hat%'
           OR serviceinfo2 LIKE '%Red Hat%')))
    AND coalesce(date, usagedatetime) >= TIMESTAMP '{{date | sqlsafe}}'
    AND coalesce(date, usagedatetime) < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
;
