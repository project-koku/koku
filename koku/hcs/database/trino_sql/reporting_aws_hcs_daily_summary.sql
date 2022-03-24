-- "SELECT *, '10001' as ebs_account_id from aws_line_items where bill_billingentity = 'AWS Marketplace' and product_productname like '%Red Hat%';"
SELECT *, '10001' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE bill_billingentity = 'AWS Marketplace'
    AND product_productname like '%Red Hat%'

-- SELECT *, '{{schema_name | sqlsafe}}' as ebs_account_id
-- FROM hive.'{{schema_name | sqlsafe}}'.{{table | sqlsafe}}
-- WHERE bill_billingentity = 'AWS Marketplace'
--     AND product_productname like '%Red Hat%'
--     AND lineitem_usagestartdate >= TIMESTAMP '{{date | sqlsafe}}'
--     AND lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
