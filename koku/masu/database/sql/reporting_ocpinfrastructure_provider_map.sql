
{% if aws_provider_uuid or ocp_provider_uuid %}
    SELECT c.provider_id as ocp_uuid,
        p.uuid as infra_uuid,
        p.type
    FROM {{schema_name | sqlsafe}}.reporting_aws_compute_summary_p as aws
    JOIN {{schema_name | sqlsafe}}.reporting_ocp_nodes as ocp
        ON ocp.resource_id = ANY(aws.resource_ids)
    JOIN {{schema_name | sqlsafe}}.reporting_ocp_clusters as c
        ON ocp.cluster_id = c.uuid
    JOIN public.api_provider as p
        ON aws.source_uuid = p.uuid
    WHERE aws.usage_start >= {{start_date}}::date
        AND aws.usage_start <= {{end_date}}::date
        AND ocp.resource_id is not null
        AND ocp.resource_id != ''
        {% if aws_provider_uuid %}
        AND aws.source_uuid = {{aws_provider_uuid}}
        {% endif %}
        {% if ocp_provider_uuid %}
        AND c.provider_id = {{ocp_provider_uuid}}
        {% endif %}
    GROUP BY c.provider_id, p.uuid, p.type
{% endif %}

{% if ocp_provider_uuid  %}
    UNION
{% endif %}

{% if azure_provider_uuid or ocp_provider_uuid %}
    SELECT c.provider_id as ocp_uuid,
        p.uuid as infra_uuid,
        p.type
    FROM (
        SELECT azure.source_uuid,
            instance_id
        FROM {{schema_name | sqlsafe}}.reporting_azure_compute_summary_p as azure,
            unnest(instance_ids) as instance_ids(instance_id)
        WHERE azure.usage_start >= {{start_date}}::date
            AND azure.usage_start <= {{end_date}}::date
            {% if azure_provider_uuid %}
            AND azure.source_uuid = {{azure_provider_uuid}}
            {% endif %}
    ) as azure
    JOIN {{schema_name | sqlsafe}}.reporting_ocp_nodes as ocp
        ON split_part(azure.instance_id, '/', 9) = ocp.node
    JOIN {{schema_name | sqlsafe}}.reporting_ocp_clusters as c
        ON ocp.cluster_id = c.uuid
    JOIN public.api_provider as p
        ON azure.source_uuid = p.uuid
    WHERE ocp.resource_id is not null
        AND ocp.resource_id != ''
        {% if ocp_provider_uuid %}
        AND c.provider_id = {{ocp_provider_uuid}}
        {% endif %}
    GROUP BY c.provider_id, p.uuid, p.type

{% endif %}
