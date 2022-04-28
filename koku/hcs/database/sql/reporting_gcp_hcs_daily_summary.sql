SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE usage_start_time >= TIMESTAMP '{{date | sqlsafe}}'
    AND usage_end_time < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
