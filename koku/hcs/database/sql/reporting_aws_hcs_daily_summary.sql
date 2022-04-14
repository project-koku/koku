SELECT *, '{{ebs_acct_num | sqlsafe}}' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE bill_billingentity = 'AWS Marketplace'
    AND lineitem_legalentity like '%Red Hat%'
    AND lineitem_usagestartdate >= TIMESTAMP '{{date | sqlsafe}}'
    AND lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
