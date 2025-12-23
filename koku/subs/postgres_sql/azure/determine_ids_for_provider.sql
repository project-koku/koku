SELECT
  DISTINCT COALESCE(NULLIF(subscriptionid, ''), subscriptionguid)
FROM {{schema | sqlsafe}}.azure_line_items
WHERE source={{source_uuid | string}}
  AND year={{year}}
  AND month={{month}}
  AND metercategory = 'Virtual Machines'
  AND lower(additionalinfo)::json->>'vcpus' IS NOT NULL
  AND lower(tags)::json->>'com_redhat_rhel' IS NOT NULL
  AND COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) NOT IN (
    SELECT
      DISTINCT usage_id
    FROM {{schema | sqlsafe}}.reporting_subs_id_map
    WHERE source_uuid!={{source_uuid}}
  )
