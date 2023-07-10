SELECT
  lineitem_resourceid as instance_id,
  identity_timeinterval as tstamp,
  product_vcpu as cpu_count,
  lineitem_usageaccountid as billing_account_id,
  coalesce(
    json_extract_scalar(
      tags, '$.com_redhat_rhel_variant'
    ),
    'Server'
  ) as variant,
  coalesce(
    json_extract_scalar(tags, '$.com_redhat_rhel_usage'),
    'Production'
  ) as usage,
  coalesce(
    json_extract_scalar(tags, '$.com_redhat_rhel_sla'),
    'Premium'
  ) as sla
FROM
  (
    SELECT
      lineitem_resourceid,
      identity_timeinterval,
      product_vcpu,
      lineitem_usageaccountid,
      cast(
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
