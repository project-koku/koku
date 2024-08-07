SELECT
    resource_id,
    CONCAT(sub, ':', rg, ':', vmname) as instance_key,
    CASE
        WHEN max_date < date_add('day', -2, current_date) THEN max_date
        ELSE date_add('day', -1, max_date)
    END
FROM (
    SELECT
     COALESCE(NULLIF(resourceid, ''), instanceid) as resource_id,
     COALESCE(NULLIF(subscriptionid, ''), subscriptionguid) as sub,
     resourcegroup as rg,
     -- if the VMName isn't present in additionalinfo, the end of the resourceid should be the VMName
     COALESCE(json_extract_scalar(lower(additionalinfo), '$.vmname'), regexp_extract(COALESCE(NULLIF(resourceid, ''), instanceid), '([^/]+$)')) as vmname,
     max(COALESCE(date, usagedatetime))as max_date
   FROM
     hive.{{schema | sqlsafe}}.azure_line_items
   WHERE
    source={{source_uuid}}
    AND year={{year}}
    AND month={{month}}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(tags), '$.com_redhat_rhel') IS NOT NULL
    AND (subscriptionid = {{usage_account}} or subscriptionguid = {{usage_account}})
    {% if excluded_ids %}
        and coalesce(NULLIF(resourceid, ''), instanceid) NOT IN {{excluded_ids | inclause}}
    {% endif %}
   GROUP BY resourceid, instanceid, subscriptionguid, subscriptionid, resourcegroup, json_extract_scalar(lower(additionalinfo), '$.vmname')
)
