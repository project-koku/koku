
{% if aws_provider_uuid or ocp_provider_uuid %}
    SELECT rp.provider_id as ocp_uuid,
        p.uuid as infra_uuid,
        p.type
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily as aws
    JOIN {{schema | sqlsafe}}.reporting_awscostentrybill as bill
        ON aws.cost_entry_bill_id = bill.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp
        ON date(aws.usage_start) = date(ocp.usage_start)
            AND aws.resource_id = ocp.resource_id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as rp
        ON ocp.report_period_id = rp.id
    JOIN public.api_provider as p
        ON bill.provider_id = p.uuid
    WHERE date(aws.usage_start) >= {{start_date}}
        AND date(aws.usage_start) <= {{end_date}}
        AND date(ocp.usage_start) >= {{start_date}}
        AND date(ocp.usage_start) <= {{end_date}}
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
    FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily as azure
    JOIN {{schema | sqlsafe}}.reporting_azurecostentryproductservice as aps
            ON azure.cost_entry_product_id = aps.id
    JOIN {{schema | sqlsafe}}.reporting_azurecostentrybill as bill
        ON azure.cost_entry_bill_id = bill.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp
        ON split_part(aps.instance_id, '/', 9) = ocp.node
            AND date(azure.usage_date_time) = date(ocp.usage_start)
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as rp
        ON ocp.report_period_id = rp.id
    JOIN public.api_provider as p
        ON bill.provider_id = p.uuid
    WHERE date(azure.usage_date_time) >= {{start_date}}
        AND date(azure.usage_date_time) <= {{end_date}}
        AND date(ocp.usage_start) >= {{start_date}}
        AND date(ocp.usage_start) <= {{end_date}}
        {% if azure_provider_uuid %}
        AND bill.provider_id = {{azure_provider_uuid}}
        {% endif %}
        {% if ocp_provider_uuid %}
        AND rp.provider_id = {{ocp_provider_uuid}}
        {% endif %}
    GROUP BY rp.provider_id, p.uuid, p.type
{% endif %}
