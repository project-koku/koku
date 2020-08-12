CREATE TEMPORARY TABLE reporting_ocp_infrastructure_cost_{{uuid | sqlsafe}} AS (
    SELECT ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.pod_labels,
        sum(ocp_aws.unblended_cost + ocp_aws.markup_cost) AS infra_cost,
        sum(ocp_aws.pod_cost + ocp_aws.project_markup_cost) AS project_infra_cost
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
    WHERE ocp_aws.usage_start >= {{start_date}}::date
        AND ocp_aws.usage_start <= {{end_date}}::date
        AND ocp_aws.cluster_id = {{cluster_id}}
    GROUP BY ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.pod_labels

    UNION

    SELECT ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.pod_labels,
        sum(ocp_azure.pretax_cost + ocp_azure.markup_cost) AS infra_cost,
        sum(ocp_azure.pod_cost + ocp_azure.project_markup_cost) AS project_infra_cost
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary AS ocp_azure
    WHERE ocp_azure.usage_start >= {{start_date}}::date
        AND ocp_azure.usage_start <= {{end_date}}::date
        AND ocp_azure.cluster_id = {{cluster_id}}
    GROUP BY ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.pod_labels
)
;

UPDATE reporting_ocpusagelineitem_daily_summary ods
    SET infrastructure_raw_cost = coalesce(ic.infra_cost, 0::numeric),
        infrastructure_project_raw_cost = coalesce(ic.project_infra_cost, 0::numeric)
    FROM reporting_ocp_infrastructure_cost_{{uuid | sqlsafe}} AS ic
    WHERE ic.data_source = 'Pod'
        AND ods.report_period_id = ic.report_period_id
        AND ods.usage_start = date(ic.usage_start)
        AND ods.cluster_id = ic.cluster_id
        AND ods.cluster_alias = ic.cluster_alias
        AND ods.namespace = ic.namespace
        AND ods.data_source = ic.data_source
        AND ods.node = ic.node
        AND ic.pod_labels @> ods.pod_labels
;

UPDATE reporting_ocpusagelineitem_daily_summary ods
    SET infrastructure_raw_cost = coalesce(ic.infra_cost, 0::numeric),
        infrastructure_project_raw_cost = coalesce(ic.project_infra_cost, 0::numeric)
    FROM reporting_ocp_infrastructure_cost_{{uuid | sqlsafe}} AS ic
    WHERE ic.data_source = 'Storage'
        AND ods.report_period_id = ic.report_period_id
        AND ods.usage_start = date(ic.usage_start)
        AND ods.cluster_id = ic.cluster_id
        AND ods.cluster_alias = ic.cluster_alias
        AND ods.namespace = ic.namespace
        AND ods.data_source = ic.data_source
        AND ods.node = ic.node
        AND ic.pod_labels @> ods.volume_labels
;
