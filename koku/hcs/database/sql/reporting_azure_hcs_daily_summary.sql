SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id, '{{org_id | sqlsafe}}' as org_id
FROM hive.{{schema_name | sqlsafe}}.{{table | sqlsafe}}
WHERE source = '{{provider_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND publishertype = 'Marketplace'
    AND (publishername like '%Red Hat%'
        OR ((publishername = 'Microsoft' OR publishername = 'Azure') AND (
           metersubcategory like '%Red Hat%'
           OR serviceinfo2 like '%Red Hat%')))
    AND coalesce(date, usagedatetime) >= TIMESTAMP '{{date | sqlsafe}}'
    AND coalesce(date, usagedatetime) < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
