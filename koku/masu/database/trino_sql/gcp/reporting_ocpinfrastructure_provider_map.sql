WITH cte_gcp_resource_name AS (
    SELECT DISTINCT gcp.resource_name,
        gcp.source
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    WHERE gcp.usage_start_time >= {{start_date}}
        AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
        {% if gcp_provider_uuid -%}
        AND gcp.source = {{gcp_provider_uuid}}
        {% endif -%}
        AND gcp.year = {{year}}
        AND gcp.month = {{month}}
),
cte_ocp_nodes AS (
    {% if ocp_provider_uuid -%}
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= {{start_date}}
        AND ocp.interval_start < date_add('day', 1, {{end_date}})
        AND ocp.node IS NOT NULL
        AND ocp.node != ''
        AND ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND ocp.month = {{month}}
    {% else -%}
    SELECT DISTINCT ocp.node,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    INNER JOIN postgres.public.api_provider as provider
        on ocp.source = cast(provider.uuid as varchar)
    WHERE ocp.interval_start >= {{start_date}}
    AND ocp.interval_start < date_add('day', 1, {{end_date}})
    AND ocp.node IS NOT NULL
        AND ocp.node != ''
    AND ocp.year = {{year}}
    AND ocp.month = {{month}}
    AND provider.type = 'OCP'
    and provider.infrastructure_id IS NULL
    {% endif -%}
)
SELECT DISTINCT ocp.source as ocp_uuid,
    gcp.source as infra_uuid,
    api_provider.type as type
FROM cte_gcp_resource_name AS gcp
JOIN cte_ocp_nodes AS ocp
    ON strpos(gcp.resource_name, ocp.node) != 0
JOIN postgres.{{schema | sqlsafe}}.reporting_tenant_api_provider as api_provider
    ON gcp.source = cast(api_provider.uuid as varchar)

{% if gcp_provider_uuid -%}
UNION

SELECT CAST(uuid AS varchar),
    {{gcp_provider_uuid}},
    infra_uuid.infrastructure_type
FROM postgres.public.api_provider AS provider_union
JOIN postgres.public.api_providerinfrastructuremap AS infra_uuid
    ON provider_union.infrastructure_id = infra_uuid.id
WHERE CAST(infrastructure_provider_id AS varchar) = {{gcp_provider_uuid}}
{% endif -%}
