SELECT
  COUNT(*)
FROM
    hive.{{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid | string }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(lower(tags)), '$.com_redhat_rhel') IS NOT NULL
    AND (subscriptionid = {{usage_account}} or subscriptionguid = {{usage_account}})
    -- ensure there is usage
    AND ceil(quantity) > 0
    AND (
        {% for item in resources %}
            (
                resourceid = {{item.rid}} AND
                date >= {{item.start}} AND
                date <= {{item.end}}
            )
            {% if not loop.last %}
                OR
            {% endif %}
        {% endfor %}
        )
