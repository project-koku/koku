SELECT
  DISTINCT COALESCE(NULLIF(subscriptionid, ''), subscriptionguid)
FROM hive.{{schema | sqlsafe}}.azure_line_items
WHERE source={{source_uuid | string}}
  AND year={{year}}
  AND month={{month}}
  AND metercategory = 'Virtual Machines'
  AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
  AND json_extract_scalar(lower(tags), '$.com_redhat_rhel') IS NOT NULL
  AND COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) NOT IN (
    SELECT
      DISTINCT usage_id
    FROM postgres.{{schema | sqlsafe}}.reporting_subs_id_map
    WHERE source_uuid!= cast({{source_uuid}} as uuid)
  )
