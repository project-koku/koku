SELECT
    resource_id,
    CONCAT(sub, ':', rg, ':', vmname) as instance_key,
    CASE
        WHEN max_date < current_date - INTERVAL '2 days' THEN max_date
        ELSE max_date - INTERVAL '1 day'
    END
FROM (
    SELECT
     resourceid as resource_id,
     COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) as sub,
     resourcegroup as rg,
     -- if the VMName isn't present in additionalinfo, the end of the resourceid should be the VMName
     COALESCE(lower(additionalinfo)::json->>'vmname', (regexp_match(resourceid, '([^/]+$)'))[1]) as vmname,
     max(date) max_date
   FROM
     {{schema | sqlsafe}}.azure_line_items
   WHERE
    source={{source_uuid | string}}
    AND year={{year}}
    AND month={{month}}
    AND metercategory = 'Virtual Machines'
    AND lower(additionalinfo)::json->>'vcpus' IS NOT NULL
    AND lower(tags)::json->>'com_redhat_rhel' IS NOT NULL
    AND (subscriptionid = {{usage_account}} or subscriptionguid = {{usage_account}})
    AND resourceid NOT IN (
        SELECT
            DISTINCT resource_id
        FROM {{schema | sqlsafe}}.reporting_subs_last_processed_time
        WHERE source_uuid != {{source_uuid}}
            AND year={{year}}
            AND month={{month}}
    )
   GROUP BY resourceid, subscriptionguid, subscriptionid, resourcegroup, lower(additionalinfo)::json->>'vmname'
)
