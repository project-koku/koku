SELECT
  *,
  time_split[1] as subs_start_time,
  time_split[2] as subs_end_time,
  product_vcpu as subs_vcpu,
  lineitem_usageaccountid as subs_account,
  lineitem_resourceid as subs_resource_id,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_variant'))
    WHEN 'workstation' THEN 'Red Hat Enterprise Linux Workstation'
    WHEN 'hpc' THEN 'Red Hat Enterprise Linux Compute Node'
    WHEN 'sap' THEN 'SAP'
    ELSE 'Red Hat Enterprise Linux Server'
  END as subs_role,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_usage'))
    WHEN 'development/test' THEN 'Development/Test'
    WHEN 'disaster recovery' THEN 'Disaster Recovery'
    ELSE 'Production'
  END as subs_usage,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_sla'))
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
  END as subs_conversion
FROM
  (
    SELECT *,
      split(identity_timeinterval, '/') as time_split,
      cast(
        transform_keys(
          map_filter(
            cast(
              json_parse(resourcetags) as map(varchar, varchar)
            ),
            (k, v) -> contains(
              ARRAY[ 'com_redhat_rhel',
              'com_redhat_rhel_variant',
              'com_redhat_rhel_usage',
              'com_redhat_rhel_sla',
              'com_redhat_rhel_addon',
              'com_redhat_rhel_conversion'],
              lower(k)
            )
          ),
          (k, v) -> lower(k)
        ) as json
      ) as tags
    from
      hive.{{schema | sqlsafe}}.aws_line_items
    WHERE
      source = {{ source_uuid | string }}
      AND year = {{ year }}
      AND month = {{ month }}
      AND lineitem_productcode = 'AmazonEC2'
      AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage', 'DiscountedUsage')
      AND product_vcpu != ''
      AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
      AND lineitem_usageaccountid = {{usage_account}}
      AND (
        {% for item in resources %}
            (
                lineitem_resourceid = {{item.rid}} AND
                lineitem_usagestartdate >= {{item.start}} AND
                lineitem_usagestartdate <= {{item.end}}
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
  )
WHERE json_extract_scalar(tags, '$.com_redhat_rhel') IS NOT NULL
