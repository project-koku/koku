
CREATE TEMPORARY TABLE ocp_infrastructure_temp AS (
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
)
;

WITH cte_aws_infrastructure_uuid_temp AS (
    SELECT provider.uuid as aws_uuid,
        provider.type,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrybill as awsbill
    JOIN ocp_infrastructure_temp as ocp_infra_temp
        ON awsbill.id = ocp_infra_temp.cost_entry_bill_id
    JOIN public.api_provider as provider
        ON provider.uuid = awsbill.provider_id
),
cte_ocp_uuid_temp AS (
    SELECT provider.uuid as ocp_uuid,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.report_period_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagereportperiod as ocprp
    JOIN ocp_infrastructure_temp as ocp_infra_temp
        ON ocprp.id = ocp_infra_temp.report_period_id
    JOIN public.api_provider as provider
        ON provider.uuid = ocprp.provider_id
)
SELECT ocp.ocp_uuid,
    aws.aws_uuid,
    aws.type
FROM cte_aws_infrastructure_uuid_temp as aws
JOIN cte_ocp_uuid_temp as ocp
    ON aws.cost_entry_bill_id = ocp.cost_entry_bill_id
        AND aws.report_period_id = ocp.report_period_id
;
