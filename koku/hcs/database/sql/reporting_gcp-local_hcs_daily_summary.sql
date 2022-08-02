SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id, '{{org_id | sqlsafe}}' as org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE sku_description LIKE 'Licensing Fee for RedHat%'
