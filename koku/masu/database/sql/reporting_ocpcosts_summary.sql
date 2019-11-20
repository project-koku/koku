CREATE TEMPORARY TABLE reporting_ocp_infrastructure_cost AS (
    SELECT ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.pod,
        ocp_aws.node,
        ocp_aws.pod_labels,
        sum(ocp_aws.unblended_cost) AS infra_cost,
        sum(ocp_aws.pod_cost) AS project_infra_cost
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
    WHERE date(ocp_aws.usage_start) >= {{start_date}}
        AND date(ocp_aws.usage_start) <= {{end_date}}
        AND ocp_aws.cluster_id = {{cluster_id}}
    GROUP BY ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.pod,
        ocp_aws.node,
        ocp_aws.pod_labels

    UNION

    SELECT ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.pod,
        ocp_azure.node,
        ocp_azure.pod_labels,
        sum(ocp_azure.pretax_cost) AS infra_cost,
        sum(ocp_azure.pod_cost) AS project_infra_cost
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary AS ocp_azure
    WHERE date(ocp_azure.usage_start) >= {{start_date}}
        AND date(ocp_azure.usage_start) <= {{end_date}}
        AND ocp_azure.cluster_id = {{cluster_id}}
    GROUP BY ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.pod,
        ocp_azure.node,
        ocp_azure.pod_labels
)
;

UPDATE reporting_ocpusagelineitem_daily_summary ods
    SET infra_cost = ic.infra_cost,
        project_infra_cost = ic.project_infra_cost
    FROM reporting_ocp_infrastructure_cost AS ic
    WHERE ic.data_source = 'Pod'
        AND ods.report_period_id = ic.report_period_id
        AND date(ods.usage_start) = date(ic.usage_start)
        AND ods.cluster_id = ic.cluster_id
        AND ods.cluster_alias = ic.cluster_alias
        AND ods.namespace = ic.namespace
        AND ods.data_source = ic.data_source
        AND ods.pod = ic.pod
        AND ods.node = ic.node
        AND ods.pod_labels = ic.pod_labels
;

UPDATE reporting_ocpusagelineitem_daily_summary ods
    SET infra_cost = ic.infra_cost,
        project_infra_cost = ic.project_infra_cost
    FROM reporting_ocp_infrastructure_cost AS ic
    WHERE ic.data_source = 'Storage'
        AND ods.report_period_id = ic.report_period_id
        AND date(ods.usage_start) = date(ic.usage_start)
        AND ods.cluster_id = ic.cluster_id
        AND ods.cluster_alias = ic.cluster_alias
        AND ods.namespace = ic.namespace
        AND ods.data_source = ic.data_source
        AND ods.pod = ic.pod
        AND ods.node = ic.node
        AND ods.volume_labels = ic.pod_labels
;
