
WITH cte_azure_instances AS (
    SELECT DISTINCT split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) as instance,
        azure.source
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    WHERE coalesce(azure.date, azure.usagedatetime) >= {{start_date}}
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, {{end_date}})
        {% if azure_provider_uuid %}
        AND azure.source = {{azure_provider_uuid}}
        {% endif %}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
),
cte_ocp_nodes AS (
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= {{start_date}}
        AND ocp.interval_start < date_add('day', 1, {{end_date}})
        AND ocp.node IS NOT NULL
        AND ocp.node != ''
        {% if ocp_provider_uuid %}
        AND ocp.source = {{ocp_provider_uuid}}
        {% endif %}
        AND ocp.year = {{year}}
        AND ocp.month = {{month}}
)
SELECT DISTINCT ocp.source as ocp_uuid,
    azure.source as infra_uuid,
    api_provider.type as type
FROM cte_azure_instances AS azure
JOIN cte_ocp_nodes AS ocp
    ON ocp.node = azure.instance
JOIN postgres.{{schema | sqlsafe}}.reporting_tenant_api_provider as api_provider
    ON azure.source = cast(api_provider.uuid as varchar)
