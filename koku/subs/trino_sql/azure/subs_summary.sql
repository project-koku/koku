SELECT
  *,
  with_timezone(COALESCE(date, usagedatetime), 'UTC') as subs_start_time,
  with_timezone(date_add('day', 1, COALESCE(date, usagedatetime)), 'UTC') as subs_end_time,
  json_extract_scalar(lower(additionalinfo), '$.vcpus') as subs_vcpu,
  COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) as subs_account,
  regexp_extract(COALESCE(NULLIF(resourceid, ''), instanceid), '([^/]+$)') as subs_resource_id,
  CAST(ceil(coalesce(nullif(quantity, 0), usagequantity)) AS INTEGER) as subs_usage_quantity,
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
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel'))
    WHEN 'rhel 7 els' THEN
      CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_variant'))
        WHEN 'sap' THEN '69-204-146'
        WHEN 'hpc' THEN '76'
        ELSE '69-204'
      END
    WHEN 'rhel 8 els' THEN
      CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_variant'))
        WHEN 'sap' THEN '479-204-241'
        WHEN 'hpc' THEN '479'
        ELSE '479-204'
      END
    ELSE '479'
  END as subs_product_ids
  COALESCE(lower(json_extract_scalar(lower(tags), '$.com_redhat_rhel_instance')), '') as subs_instance
FROM
    hive.{{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(lower(tags)), '$.com_redhat_rhel') IS NOT NULL
    -- ensure there is usage
    AND ceil(coalesce(nullif(quantity, 0), usagequantity)) > 0
    AND (
        {% for item in resources %}
            (
                coalesce(NULLIF(resourceid, ''), instanceid) = {{item.rid}} AND
                coalesce(date, usagedatetime) >= {{item.start}} AND
                coalesce(date, usagedatetime) <= {{item.end}}
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
