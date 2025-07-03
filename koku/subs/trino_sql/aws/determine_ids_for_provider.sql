SELECT
  DISTINCT lineitem_usageaccountid
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid | string}}
  AND year={{year}}
  AND month={{month}}
  AND lineitem_productcode = 'AmazonEC2'
  AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
  AND lineitem_usageaccountid NOT IN (
    SELECT
      DISTINCT usage_id
    FROM postgres.{{schema | sqlsafe}}.reporting_subs_id_map
    WHERE source_uuid!=cast({{source_uuid}} as uuid)
  )
