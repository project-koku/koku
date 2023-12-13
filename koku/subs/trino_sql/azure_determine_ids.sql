SELECT
  DISTINCT COALESCE(
    NULLIF(subscriptionid, ''),
    subscriptionguid
  )
FROM
  hive.{{schema | sqlsafe}}.azure_line_items
WHERE
  source = {{source_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  { % if excluded_ids % }
  AND COALESCE(
        NULLIF(subscriptionid, ''),
        subscriptionguid
    ) NOT IN {{excluded_ids | inclause}}
  { % endif % }
