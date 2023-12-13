SELECT
  DISTINCT lineitem_usageaccountid
FROM
  hive.{{schema | sqlsafe}}.aws_line_items
WHERE
  source = {{source_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  { % if excluded_ids % }
    AND lineitem_usageaccountid NOT IN {{excluded_ids | inclause}}
  { % endif % }
