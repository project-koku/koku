SELECT count(*)
    FROM
      hive.{{schema | sqlsafe}}.aws_line_items
    WHERE
      source = {{ source_uuid }}
      AND year = {{ year }}
      AND month = {{ month }}
      AND lineitem_productcode = 'AmazonEC2'
      AND lineitem_lineitemtype IN ('Usage', 'SavingsPlanCoveredUsage')
      AND product_vcpu != ''
      AND strpos(lower(resourcetags), 'com_redhat_rhel') > 0
      AND (
        {% for item in resources %}
            (
                lineitem_resourceid = {{item.rid}} AND
                lineitem_usagestartdate >= {{item.start}} AND
                lineitem_usagestartdate <= {{item.end}}
            )
            {% if not loop.last %}
                OR
            {% endif %}
        {% endfor %}
        )
