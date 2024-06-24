SELECT DISTINCT COALESCE(NULLIF(subscriptionid, ''), subscriptionguid)
FROM hive.{{schema | sqlsafe}}.azure_line_items
WHERE source={{source_uuid}}
  AND year={{year}}
  AND month={{month}}
  AND metercategory = 'Virtual Machines'
  AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
  AND json_extract_scalar(lower(tags), '$.com_redhat_rhel') IS NOT NULL
  {% if excluded_ids %}
    AND COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) NOT IN {{excluded_ids | inclause}}
  {% endif %}
