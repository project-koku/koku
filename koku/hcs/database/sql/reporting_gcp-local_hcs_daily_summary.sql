SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id, '{{org_id | sqlsafe}}' as org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE sku_description LIKE 'Licensing Fee for RedHat%'
    AND source = '{{provider_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND usage_start_time >= TIMESTAMP '{{date | sqlsafe}}'
    AND usage_start_time < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
