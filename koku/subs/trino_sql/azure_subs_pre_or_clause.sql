SELECT
  *,
  coalesce(date, usagedatetime) as subs_start_time,
  date_add('day', 1, coalesce(date, usagedatetime)) as subs_end_time,
  json_extract_scalar(lower(additionalinfo), '$.vcpus') as subs_vcpu,
  subscriptionid as subs_account,
  regexp_extract(coalesce(resourceid, instancename), '([^/]+$)') as subs_resource_id,
  CASE lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_variant'))
    WHEN 'workstation' THEN 'Red Hat Enterprise Linux Workstation'
    ELSE 'Red Hat Enterprise Linux Server'
  END as subs_role,
  CASE lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_usage'))
    WHEN 'development/test' THEN 'Development/Test'
    WHEN 'disaster recovery' THEN 'Disaster Recovery'
    ELSE 'Production'
  END as subs_usage,
  CASE lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_sla'))
    WHEN 'standard' THEN 'Standard'
    WHEN 'self-support' THEN 'Self-Support'
    ELSE 'Premium'
  END as subs_sla,
  CASE lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel'))
    WHEN 'rhel 7 els' THEN '69-204'
    WHEN 'rhel 8 els' THEN '479-204'
    ELSE '479'
  END as subs_product_ids
FROM
    hive.{{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(lower(tags)), '$.com_redhat_rhel') IS NOT NULL
