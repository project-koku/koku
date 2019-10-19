CREATE TEMPORARY TABLE aws_daily_tags_temp AS (
    SELECT aws.usage_start,
        aws.cost_entry_bill_id,
        aws.resource_id,
        LOWER(key) as key,
        value
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily as aws,
        jsonb_each_text(aws.tags) labels
)
;

CREATE TEMPORARY TABLE ocp_infrastructure_temp AS (
    SELECT aws.cost_entry_bill_id,
        ocp.cluster_id
    FROM aws_daily_tags_temp as aws
    JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as ocp
        ON aws.usage_start::date = ocp.usage_start::date
            AND (aws.resource_id = ocp.resource_id
                OR (aws.key = 'openshift_project' AND aws.value = ocp.namespace)
                OR (aws.key = 'openshift_node' AND aws.value = ocp.node)
                OR (aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_id)
                OR (aws.key = 'openshift_cluster' AND aws.value = ocp.cluster_alias))
    WHERE date(aws.usage_start) >= {{start_date}}
        AND date(aws.usage_start) <= {{end_date}}
    GROUP BY aws.cost_entry_bill_id, ocp.cluster_id
)
;

CREATE TEMPORARY TABLE aws_infrastructure_uuid_temp AS (
    SELECT provider.uuid as aws_uuid,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.cluster_id
    FROM {{schema | sqlsafe}}.reporting_awscostentrybill as awsbill
    JOIN ocp_infrastructure_temp as ocp_infra_temp
        ON awsbill.id = ocp_infra_temp.cost_entry_bill_id
    JOIN public.api_provider as provider
        ON provider.id = awsbill.provider_id
)
;

CREATE TEMPORARY TABLE ocp_uuid_temp AS (
    SELECT provider.uuid as ocp_uuid,
        ocp_infra_temp.cost_entry_bill_id,
        ocp_infra_temp.cluster_id
    FROM public.api_providerauthentication as authentication
    JOIN public.api_provider as provider
        ON provider.authentication_id = authentication.id
    JOIN ocp_infrastructure_temp as ocp_infra_temp
        ON authentication.provider_resource_name = ocp_infra_temp.cluster_id
)
;

SELECT aws.aws_uuid as aws_uuid,
    ocp.ocp_uuid as ocp_uuid,
    ocp.cluster_id
FROM aws_infrastructure_uuid_temp as aws
JOIN ocp_uuid_temp as ocp
    ON aws.cost_entry_bill_id = ocp.cost_entry_bill_id
        AND aws.cluster_id = ocp.cluster_id
;
