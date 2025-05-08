SELECT
  *,
  with_timezone(date, 'UTC') as subs_start_time,
  with_timezone(date_add('day', 1, date), 'UTC') as subs_end_time,
  json_extract_scalar(lower(additionalinfo), '$.vcpus') as subs_vcpu,
  COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) as subs_account,
  regexp_extract(resourceid, '([^/]+$)') as subs_resource_id,
  CAST(ceil(quantity) AS INTEGER) as subs_usage_quantity,
  CASE lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_variant'))
    WHEN 'workstation' THEN 'Red Hat Enterprise Linux Workstation'
    WHEN 'hpc' THEN 'Red Hat Enterprise Linux Compute Node'
    WHEN 'sap' THEN 'SAP'
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
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel'))
    WHEN '7' THEN '69'
    WHEN '8' THEN '479'
    ELSE '479'
  END as subs_rhel_version,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_addon'))
    WHEN 'els' THEN '204'
    ELSE NULL
  END as subs_addon_id,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_conversion'))
    WHEN 'true' THEN 'true'
    ELSE 'false'
  END as subs_conversion,
  COALESCE(lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_instance')), '') as subs_instance,
  -- if the VMName isn't present in additionalinfo, the end of the resourceid should be the VMName
  COALESCE(json_extract_scalar(lower(additionalinfo), '$.vmname'), regexp_extract(resourceid, '([^/]+$)')) as subs_vmname
FROM
    hive.{{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(lower(tags)), '$.com_redhat_rhel') IS NOT NULL
    AND (subscriptionid = {{usage_account}} or subscriptionguid = {{usage_account}})
    -- ensure there is usage
    AND ceil(quantity) > 0
    AND (
        {% for item in resources %}
            (
                resourceid = {{item.rid}} AND
                date >= {{item.start}} AND
                date <= {{item.end}}
            )
            {% if not loop.last %}
                OR
            {% endif %}
        {% endfor %}
        )
OFFSET
    {{ offset }}
LIMIT
    {{ limit }}
