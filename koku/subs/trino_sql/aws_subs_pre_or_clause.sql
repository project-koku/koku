SELECT
  *,
  time_split[1] as subs_start_time,
  time_split[2] as subs_end_time,
  CASE lower(json_extract_scalar(tags, '$.com_redhat_rhel_variant'))
    WHEN 'workstation' THEN 'Red Hat Enterprise Linux Workstation'
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
    WHEN 'rhel 7 els' THEN '69-204'
    WHEN 'rhel 8 els' THEN '479-204'
    ELSE '479'
  END as subs_product_ids
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
      source = {{ source_uuid }}
      AND year = {{ year }}
      AND month = {{ month }}
      AND lineitem_productcode = 'AmazonEC2'
      AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage')
      AND product_vcpu != ''
      AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
