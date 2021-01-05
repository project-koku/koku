
{% if aws_provider_uuid or ocp_provider_uuid %}
    SELECT rp.provider_id as ocp_uuid,
        p.uuid as infra_uuid,
        p.type
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary as aws
    JOIN {{schema | sqlsafe}}.reporting_awscostentrybill as bill
        ON aws.cost_entry_bill_id = bill.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON aws.usage_start = ocp.usage_start
            AND ocp.resource_id = ANY(aws.resource_ids)
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as rp
        ON ocp.report_period_id = rp.id
    JOIN public.api_provider as p
        ON bill.provider_id = p.uuid
    WHERE aws.usage_start >= {{start_date}}::date
        AND aws.usage_start <= {{end_date}}::date
        AND ocp.usage_start >= {{start_date}}::date
        AND ocp.usage_start <= {{end_date}}::date
        {% if aws_provider_uuid %}
        AND bill.provider_id = {{aws_provider_uuid}}
        {% endif %}
        {% if ocp_provider_uuid %}
        AND rp.provider_id = {{ocp_provider_uuid}}
        {% endif %}
    GROUP BY rp.provider_id, p.uuid, p.type
{% endif %}

{% if ocp_provider_uuid  %}
    UNION
{% endif %}

{% if azure_provider_uuid or ocp_provider_uuid %}
    SELECT rp.provider_id as ocp_uuid,
        p.uuid as infra_uuid,
        p.type
    FROM (
        SELECT azure.cost_entry_bill_id,
            azure.usage_start,
            instance_id
        FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily_summary as azure,
            unnest(instance_ids) as instance_ids(instance_id)
        WHERE azure.usage_start >= {{start_date}}::date
            AND azure.usage_start <= {{end_date}}::date
            {% if azure_provider_uuid %}
            AND azure.source_uuid = {{azure_provider_uuid}}
            {% endif %}
    ) as azure
    JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as bill
        ON azure.cost_entry_bill_id = bill.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON split_part(azure.instance_id, '/', 9) = ocp.node
            AND azure.usage_start = ocp.usage_start
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as rp
        ON ocp.report_period_id = rp.id
    JOIN public.api_provider as p
        ON bill.provider_id = p.uuid
    WHERE ocp.usage_start >= {{start_date}}::date
        AND ocp.usage_start <= {{end_date}}::date
        {% if ocp_provider_uuid %}
        AND rp.provider_id = {{ocp_provider_uuid}}
        {% endif %}
    GROUP BY rp.provider_id, p.uuid, p.type
{% endif %}
