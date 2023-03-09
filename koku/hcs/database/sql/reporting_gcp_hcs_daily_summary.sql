SELECT
*,
'{{ebs_acct_num | sqlsafe}}' AS ebs_account_id,
'{{org_id | sqlsafe}}' AS org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE (sku_description LIKE '%RedHat%'
    OR sku_description LIKE '%Red Hat%'
    OR service_description LIKE '%Red Hat%')
    AND source = '{{provider_uuid | sqlsafe}}'
    AND year = '{{year | sqlsafe}}'
    AND month = '{{month | sqlsafe}}'
    AND usage_start_time >= TIMESTAMP '{{date | sqlsafe}}'
    AND usage_start_time < date_add('day', 1, TIMESTAMP '{{date | sqlsafe}}')
;
