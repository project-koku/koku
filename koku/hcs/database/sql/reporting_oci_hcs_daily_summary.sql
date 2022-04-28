SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
