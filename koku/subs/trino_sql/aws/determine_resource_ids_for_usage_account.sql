SELECT lineitem_resourceid, max(lineitem_usagestartdate)
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid}}
AND year={{year}}
AND month={{month}}
AND lineitem_productcode = 'AmazonEC2'
AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
AND lineitem_usageaccountid = {{usage_account}}
    {% if excluded_ids %}
        AND lineitem_resourceid NOT IN {{excluded_ids | inclause}}
    {% endif %}
GROUP BY lineitem_resourceid



SELECT
    lineitem_resourceid,
    max(lineitem_usagestartdate)
FROM hive.{{schema | sqlsafe}}.aws_line_items
WHERE source={{source_uuid}}
    AND year={{year}}
    AND month={{month}}
    AND lineitem_productcode = 'AmazonEC2'
    AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
    AND lineitem_resourceid NOT IN (
        SELECT
            DISTINCT resource_id
        FROM postgres.{{schema | sqlsage}}.reporting_subs_last_processed_time
        WHERE source_uuid != cast({{source_uuid}} as uuid)
            AND year={{year}}
            AND month={{month}}
    )
GROUP BY lineitem_resourceid
