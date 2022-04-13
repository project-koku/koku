-- SELECT *, '10001' as ebs_account_id
-- FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
-- WHERE bill_billingentity = 'AWS Marketplace'
--     AND product_productname like '%Red Hat%'
SELECT *, '{{schema | sqlsafe}}' as ebs_account_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE publishertype = 'Marketplace'
    AND publishername like '%Red Hat%'
