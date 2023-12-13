WHERE
  source = {{source_uuid}}
  AND year = {{year}}
  AND month = {{month}}
  AND metercategory = 'Virtual Machines'
  AND chargetype = 'Usage'
  AND json_extract_scalar(
    lower(additionalinfo),
    '$.vcpus'
  ) IS NOT NULL
  AND json_extract_scalar(
    lower(tags),
    '$.com_redhat_rhel'
  ) IS NOT NULL
