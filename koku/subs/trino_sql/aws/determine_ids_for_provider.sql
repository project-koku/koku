SELECT DISTINCT lineitem_usageaccountid
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid}}
  AND year={{year}}
  AND month={{month}}
  AND lineitem_productcode = 'AmazonEC2'
  AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
  {% if excluded_ids %}
    AND lineitem_usageaccountid NOT IN {{excluded_ids | inclause}}
  {% endif %}
