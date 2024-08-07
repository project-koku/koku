SELECT
    resource_id,
    CASE
        WHEN max_date < date_add('day', -2, current_date) THEN max_date
        ELSE date_add('day', -1, max_date)
    END
FROM (
    SELECT
     NULLIF(resourceid, '') resource_id,
     max(date) max_date
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
        and NULLIF(resourceid, '') NOT IN {{excluded_ids | inclause}}
    {% endif %}
   GROUP BY resourceid
)
