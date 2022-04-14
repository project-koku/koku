SELECT *, '{{schema | sqlsafe}}' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE publishertype = 'Marketplace'
    AND publishername like '%Red Hat%'
    AND coalesce(date, usagedatetime) >= TIMESTAMP '{{date | sqlsafe}}'
    AND coalesce(date, usagedatetime) < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
