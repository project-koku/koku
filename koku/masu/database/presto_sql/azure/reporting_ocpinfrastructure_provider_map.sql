
WITH cte_azure_instances AS (
    SELECT DISTINCT split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) as instance,
        azure.source
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    WHERE coalesce(azure.date, azure.usagedatetime) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        {% if azure_provider_uuid %}
        AND azure.source = '{{azure_provider_uuid | sqlsafe}}'
        {% endif %}
        AND azure.year = '{{year | sqlsafe}}'
        AND azure.month = '{{month | sqlsafe}}'
),
cte_ocp_nodes AS (
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.node IS NOT NULL
        AND ocp.node != ''
        {% if ocp_provider_uuid %}
        AND ocp.source = '{{ocp_provider_uuid | sqlsafe}}'
        {% endif %}
        AND ocp.year = '{{year | sqlsafe}}'
        AND ocp.month = '{{month | sqlsafe}}'
)
SELECT DISTINCT ocp.source as ocp_uuid,
    azure.source as infra_uuid,
    'Azure' as type
FROM cte_azure_instances AS azure
JOIN cte_ocp_nodes AS ocp
    ON ocp.node = azure.instance
