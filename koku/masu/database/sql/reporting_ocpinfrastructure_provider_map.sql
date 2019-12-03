
CREATE TEMPORARY TABLE ocp_infrastructure_{{uuid | sqlsafe}} AS (
    SELECT aws.cost_entry_bill_id,
        ocp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily as aws
    JOIN {{schema | sqlsafe}}.reporting_awscostentrybill as bill
        ON aws.cost_entry_bill_id = bill.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp
        ON date(aws.usage_start) = date(ocp.usage_start)
            AND aws.resource_id = ocp.resource_id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as rp
        ON ocp.report_period_id = rp.id
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
    GROUP BY aws.cost_entry_bill_id, ocp.report_period_id

    UNION

    SELECT azure.cost_entry_bill_id,
        ocp.report_period_id
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
    GROUP BY azure.cost_entry_bill_id, ocp.report_period_id
)
;

WITH cte_infrastructure_uuid_temp AS (
    SELECT provider.uuid as infra_uuid,
        provider.type,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrybill as awsbill
    JOIN ocp_infrastructure_{{uuid | sqlsafe}} as ocp_infra_temp
        ON awsbill.id = ocp_infra_temp.cost_entry_bill_id
    JOIN public.api_provider as provider
        ON provider.uuid = awsbill.provider_id

    UNION

    SELECT provider.uuid as infra_uuid,
        provider.type,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_azurecostentrybill as azurebill
    JOIN ocp_infrastructure_{{uuid | sqlsafe}} as ocp_infra_temp
        ON azurebill.id = ocp_infra_temp.cost_entry_bill_id
    JOIN public.api_provider as provider
        ON provider.uuid = azurebill.provider_id
),
cte_ocp_uuid_temp AS (
    SELECT provider.uuid as ocp_uuid,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagereportperiod as ocprp
    JOIN ocp_infrastructure_{{uuid | sqlsafe}} as ocp_infra_temp
        ON ocprp.id = ocp_infra_temp.report_period_id
    JOIN public.api_provider as provider
        ON provider.uuid = ocprp.provider_id
)
SELECT ocp.ocp_uuid,
    infra.infra_uuid,
    infra.type
FROM cte_infrastructure_uuid_temp as infra
JOIN cte_ocp_uuid_temp as ocp
    ON infra.cost_entry_bill_id = ocp.cost_entry_bill_id
        AND infra.report_period_id = ocp.report_period_id
;
