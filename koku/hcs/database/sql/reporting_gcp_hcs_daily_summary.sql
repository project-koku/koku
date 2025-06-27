SELECT *, {{ebs_acct_num}} as ebs_account_id, {{org_id}} as org_id
FROM hive.{{schema | sqlsafe}}.{{table | sqlsafe}}
WHERE ( sku_description LIKE '%RedHat%'
    OR sku_description LIKE '%Red Hat%'
    OR  service_description LIKE '%Red Hat%')
    AND source = {{provider_uuid | string}}
    AND year = {{year}}
    AND month = {{month}}
    AND usage_start_time >= {{date}}
    AND usage_start_time < date_add('day', 1, {{date}})
