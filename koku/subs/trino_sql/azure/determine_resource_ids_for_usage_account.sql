SELECT
    resource_id,
    CONCAT(sub, ':', rg, ':', vmname) as instance_key,
    CASE
        WHEN max_date < date_add('day', -2, current_date) THEN max_date
        ELSE date_add('day', -1, max_date)
    END
FROM (
    SELECT
     resourceid as resource_id,
     COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) as sub,
     resourcegroup as rg,
     -- if the VMName isn't present in additionalinfo, the end of the resourceid should be the VMName
     COALESCE(json_extract_scalar(lower(additionalinfo), '$.vmname'), regexp_extract(resourceid, '([^/]+$)')) as vmname,
     max(date) max_date
   FROM
     hive.{{schema | sqlsafe}}.azure_line_items
   WHERE
    source={{source_uuid | string}}
    AND year={{year}}
    AND month={{month}}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(tags), '$.com_redhat_rhel') IS NOT NULL
    AND (subscriptionid = {{usage_account}} or subscriptionguid = {{usage_account}})
    AND resourceid NOT IN (
        SELECT
            DISTINCT resource_id
        FROM postgres.{{schema | sqlsafe}}.reporting_subs_last_processed_time
        WHERE source_uuid != {{source_uuid}}
            AND year={{year}}
            AND month={{month}}
    )
   GROUP BY resourceid, subscriptionguid, subscriptionid, resourcegroup, json_extract_scalar(lower(additionalinfo), '$.vmname')
)
