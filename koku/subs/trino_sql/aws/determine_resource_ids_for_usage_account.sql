SELECT lineitem_resourceid, max(lineitem_usagestartdate)
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid}}
AND year={{year}}
AND month={{month}}
AND lineitem_productcode = 'AmazonEC2'
AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
AND lineitem_usageaccountid = {{usage_account}}
GROUP BY lineitem_resourceid
