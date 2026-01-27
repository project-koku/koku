SELECT
  COUNT(*)
FROM
    {{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid | string }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND lower(additionalinfo)::json->>'vcpus' IS NOT NULL
    AND lower(lower(tags))::json->>'com_redhat_rhel' IS NOT NULL
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
