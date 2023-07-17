SELECT
  *,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_variant'))
    WHEN 'workstation' THEN 'Red Hat Enterprise Linux Workstation'
    ELSE 'Red Hat Enterprise Linux Server'
  END as subs_role,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_usage'))
    WHEN 'development/test' THEN 'Development/Test'
    WHEN 'disaster recover' THEN 'Disaster Recovery'
    ELSE 'Production'
  END as subs_usage,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_sla'))
    WHEN 'standard' THEN 'Standard'
    WHEN 'self-support' THEN 'Self-Support'
    ELSE 'Premium'
  END as subs_sla
FROM
  (
    SELECT *,
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
              'com_redhat_rhel_sla' ],
              lower(k)
            )
          ),
          (k, v) -> lower(k)
        ) as json
      ) as tags
    from
      hive.{{schema | sqlsafe}}.aws_line_items
    WHERE
      source = {{ provider_uuid }}
      AND year = {{ year }}
      AND month = {{ month }}
      AND lineitem_productcode = 'AmazonEC2'
      AND lineitem_lineitemtype = 'Usage'
      and product_vcpu IS NOT NULL
      AND lineitem_usagestartdate > {{ time_filter }}
      AND strpos(resourcetags, 'com_redhat_rhel') > 0
    OFFSET
      {{ offset }}
    LIMIT
      {{ limit }}
  )
WHERE
  lower(
    json_extract_scalar(tags, '$.com_redhat_rhel')
  ) = 'true'
