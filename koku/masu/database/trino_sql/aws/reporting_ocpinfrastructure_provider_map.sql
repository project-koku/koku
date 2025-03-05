
WITH cte_aws_resource_ids AS (
    SELECT DISTINCT lineitem_resourceid,
        aws.source
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
    WHERE aws.lineitem_usagestartdate >= {{start_date}}
        AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
        AND aws.lineitem_resourceid IS NOT NULL
        AND aws.lineitem_resourceid != ''
        {% if aws_provider_uuid -%}
        AND aws.source = {{aws_provider_uuid}}
        {% endif -%}
        AND aws.year = {{year}}
        AND aws.month = {{month}}
),
cte_ocp_resource_ids AS (
{% if ocp_provider_uuid -%}
    SELECT DISTINCT resource_id,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    WHERE ocp.interval_start >= {{start_date}}
    AND ocp.interval_start < date_add('day', 1, {{end_date}})
    AND ocp.resource_id IS NOT NULL
    AND ocp.resource_id != ''
    AND ocp.source = {{ocp_provider_uuid}}
    AND ocp.year = {{year}}
    AND ocp.month = {{month}}
{% else -%}
    SELECT DISTINCT resource_id,
        ocp.source
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS ocp
    INNER JOIN postgres.public.api_provider as provider
        on ocp.source = cast(provider.uuid as varchar)
    WHERE ocp.interval_start >= {{start_date}}
    AND ocp.interval_start < date_add('day', 1, {{end_date}})
    AND ocp.resource_id IS NOT NULL
    AND ocp.resource_id != ''
    AND ocp.year = {{year}}
    AND ocp.month = {{month}}
    AND provider.type = 'OCP'
    and provider.infrastructure_id IS NULL
{% endif -%}
)

SELECT DISTINCT ocp.source as ocp_uuid,
    aws.source as infra_uuid,
    api_provider.type as type
FROM cte_aws_resource_ids AS aws
JOIN cte_ocp_resource_ids AS ocp
    ON strpos(aws.lineitem_resourceid, ocp.resource_id) != 0
JOIN postgres.{{schema | sqlsafe}}.reporting_tenant_api_provider as api_provider
    ON aws.source = cast(api_provider.uuid as varchar)

{% if aws_provider_uuid -%}
UNION

SELECT CAST(uuid AS varchar),
    {{aws_provider_uuid}},
    infra_uuid.infrastructure_type
FROM postgres.public.api_provider AS provider_union
JOIN postgres.public.api_providerinfrastructuremap AS infra_uuid
    ON provider_union.infrastructure_id = infra_uuid.id
WHERE CAST(infrastructure_provider_id AS varchar) = {{aws_provider_uuid}}
{% endif -%}
