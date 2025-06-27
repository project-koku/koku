SELECT
    lineitem_resourceid,
    max(lineitem_usagestartdate)
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid | string}}
    AND year={{year}}
    AND month={{month}}
    AND lineitem_productcode = 'AmazonEC2'
    AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
    AND lineitem_usageaccountid = {{usage_account}}
    AND lineitem_resourceid NOT IN (
        SELECT
            DISTINCT resource_id
        FROM postgres.{{schema | sqlsafe}}.reporting_subs_last_processed_time
        WHERE source_uuid != {{source_uuid}}
            AND year={{year}}
            AND month={{month}}
    )
GROUP BY lineitem_resourceid
