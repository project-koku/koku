SELECT
  coalesce(
    NULLIF(resourceid, ''),
    instancename
  ),
  date_add(
    'day',
    -1,
    max(
      coalesce(date, usagedatetime)
    )
  )
FROM
  hive.{{schema | sqlsafe}}.azure_line_items
WHERE
  source = {{source_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  AND metercategory = 'Virtual Machines'
  AND json_extract_scalar(
    lower(additionalinfo),
    '$.vcpus'
  ) IS NOT NULL
  AND json_extract_scalar(
    lower(tags),
    '$.com_redhat_rhel'
  ) IS NOT NULL
  AND (
    subscriptionid = {{usage_account}}
    or subscriptionguid = {{usage_account}}
  )
  { % if excluded_ids % }
    AND coalesce(
        NULLIF(resourceid, ''),
        instancename
    ) NOT IN {{excluded_ids | inclause}}
  { % endif % }
GROUP BY
  resourceid,
  instancename
