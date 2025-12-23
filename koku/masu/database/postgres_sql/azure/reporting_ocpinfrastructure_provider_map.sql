
WITH cte_azure_instances AS (
    SELECT DISTINCT split_part(azure.resourceid, '/', 9) as instance,
        azure.source
    FROM {{schema | sqlsafe}}.azure_line_items AS azure
    WHERE azure.date >= {{start_date}}
        AND azure.date < {{end_date}} + INTERVAL '1 day'
        {% if azure_provider_uuid -%}
        AND azure.source = {{azure_provider_uuid}}
        {% endif -%}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
),
cte_ocp_nodes AS (
    {% if ocp_provider_uuid -%}
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= {{start_date}}
        AND ocp.interval_start < {{end_date}} + INTERVAL '1 day'
        AND ocp.node IS NOT NULL
        AND ocp.node != ''
        AND ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND ocp.month = {{month}}
    {% else -%}
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    INNER JOIN public.api_provider as provider
        on ocp.source = provider.uuid::varchar
    WHERE ocp.interval_start >= {{start_date}}
    AND ocp.interval_start < {{end_date}} + INTERVAL '1 day'
    AND ocp.node IS NOT NULL
    AND ocp.node != ''
    AND ocp.year = {{year}}
    AND ocp.month = {{month}}
    AND provider.type = 'OCP'
    and provider.infrastructure_id IS NULL
    {% endif -%}
)
SELECT DISTINCT ocp.source as ocp_uuid,
    azure.source as infra_uuid,
    api_provider.type as type
FROM cte_azure_instances AS azure
JOIN cte_ocp_nodes AS ocp
    ON ocp.node = azure.instance
JOIN {{schema | sqlsafe}}.reporting_tenant_api_provider as api_provider
    ON azure.source = api_provider.uuid::varchar

{% if azure_provider_uuid -%}
UNION

SELECT uuid::varchar,
    {{azure_provider_uuid}},
    infra_uuid.infrastructure_type
FROM public.api_provider AS provider_union
JOIN public.api_providerinfrastructuremap AS infra_uuid
    ON provider_union.infrastructure_id = infra_uuid.id
WHERE infrastructure_provider_id::varchar = {{azure_provider_uuid}}
{% endif -%}
