{% if aws_provider_uuid or ocp_provider_uuid %}
    SELECT DISTINCT ocp.source as ocp_uuid,
        aws.source as infra_uuid,
        'AWS' as type
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        ON aws.lineitem_usagestartdate = ocp.interval_start
            AND ocp.resource_id = aws.lineitem_resourceid
    WHERE aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if aws_provider_uuid %}
        AND aws.source = '{{aws_provider_uuid | sqlsafe}}'
        AND aws.year = '{{year | sqlsafe}}'
        AND aws.month = '{{month | sqlsafe}}'
        {% endif %}
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
        {% endif %}
{% endif %}

{% if ocp_provider_uuid  %}
    UNION
{% endif %}

{% if azure_provider_uuid or ocp_provider_uuid %}
    SELECT DISTINCT ocp.source as ocp_uuid,
        azure.source as infra_uuid,
        'Azure' as type
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
        ON coalesce(azure.date, azure.usagedatetime) = ocp.interval_start
            AND ocp.node = split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9)
    WHERE coalesce(azure.date, azure.usagedatetime) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if azure_provider_uuid %}
        AND azure.source = '{{azure_provider_uuid | sqlsafe}}'
        AND azure.year = '{{year | sqlsafe}}'
        AND azure.month = '{{month | sqlsafe}}'
        {% endif %}
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
        {% endif %}
{% endif %}
