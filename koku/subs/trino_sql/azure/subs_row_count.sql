SELECT
  COUNT(*)
FROM
    hive.{{schema | sqlsafe}}.azure_line_items
WHERE
    source = {{ source_uuid }}
    AND year = {{ year }}
    AND month = {{ month }}
    AND metercategory = 'Virtual Machines'
    AND json_extract_scalar(lower(additionalinfo), '$.vcpus') IS NOT NULL
    AND json_extract_scalar(lower(lower(tags)), '$.com_redhat_rhel') IS NOT NULL
    -- ensure there is usage
    AND ceil(coalesce(nullif(quantity, 0), usagequantity)) > 0
    AND (
        {% for item in resources %}
            (
                coalesce(NULLIF(resourceid, ''), instanceid) = {{item.rid}} AND
                coalesce(date, usagedatetime) >= {{item.start}} AND
                coalesce(date, usagedatetime) <= {{item.end}}
            )
            {% if not loop.last %}
                OR
            {% endif %}
        {% endfor %}
        )
