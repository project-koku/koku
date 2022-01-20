-- Clear out old entries first
DELETE FROM postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_daily_summary_p
WHERE usage_start >= date('{{start_date | sqlsafe}}')
    AND usage_start <= date('{{end_date | sqlsafe}}')
    AND report_period_id = {{report_period_id | sqlsafe}}
;


-- Populate the daily aggregate line item data
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_daily_summary_p (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    resource_id,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    region,
    tags,
    usage_amount,
    unblended_cost,
    markup_cost,
    currency,
    unit,
    shared_projects,
    source_uuid,
    credit_amount,
    invoice_month
)
    SELECT uuid(),
        report_period_id,
        cluster_id,
        cluster_alias,
        array_agg(DISTINCT namespace) as namespace,
        node,
        resource_id,
        usage_start,
        usage_end,
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name,
        instance_type,
        service_id,
        service_alias,
        region,
        tags,
        sum(usage_amount) as usage_amount,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        max(unit) as unit,
        count(DISTINCT namespace) as shared_projects,
        source_uuid,
        sum(credit_amount) as credit_amount,
        invoice_month
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p
    WHERE report_period_id = {{report_period_id | sqlsafe}}
        AND usage_start >= date('{{start_date | sqlsafe}}')
        AND usage_start <= date('{{end_date | sqlsafe}}')
    GROUP BY report_period_id,
        cluster_id,
        cluster_alias,
        node,
        resource_id,
        usage_start,
        usage_end,
        cost_entry_bill_id,
        account_id,
        project_id,
        project_name,
        instance_type,
        service_id,
        service_alias,
        region,
        tags,
        source_uuid,
        invoice_month
;

INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    namespace,
    data_source,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    pod_labels,
    volume_labels,
    source_uuid,
    infrastructure_raw_cost,
    infrastructure_project_raw_cost,
    infrastructure_usage_cost,
    supplementary_usage_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months
)
    SELECT uuid() as uuid,
        ocp_gcp.report_period_id,
        ocp_gcp.usage_start,
        ocp_gcp.usage_start,
        ocp_gcp.cluster_id,
        ocp_gcp.cluster_alias,
        ocp_gcp.namespace,
        ocp_gcp.data_source,
        ocp_gcp.node,
        ocp_gcp.persistentvolumeclaim,
        max(ocp_gcp.persistentvolume),
        max(ocp_gcp.storageclass),
        ocp_gcp.resource_id,
        CASE WHEN ocp_gcp.data_source = 'Pod'
            THEN ocp_gcp.pod_labels
            ELSE CAST('{}' AS JSON)
        END as pod_labels,
        CASE WHEN ocp_gcp.data_source = 'Storage'
            THEN ocp_gcp.pod_labels
            ELSE CAST('{}' AS JSON)
        END as volume_labels,
        rp.provider_id as source_uuid,
        sum(ocp_gcp.unblended_cost + ocp_gcp.markup_cost) AS infrastructure_raw_cost,
        sum(ocp_gcp.pod_cost + ocp_gcp.project_markup_cost) AS infrastructure_project_raw_cost,
        CAST('{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' AS JSON) as infrastructure_usage_cost,
        CAST('{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' AS JSON) as supplementary_usage_cost,
        0 as pod_usage_cpu_core_hours,
        0 as pod_request_cpu_core_hours,
        0 as pod_limit_cpu_core_hours,
        0 as pod_usage_memory_gigabyte_hours,
        0 as pod_request_memory_gigabyte_hours,
        0 as pod_limit_memory_gigabyte_hours,
        0 as node_capacity_cpu_cores,
        0 as node_capacity_cpu_core_hours,
        0 as node_capacity_memory_gigabytes,
        0 as node_capacity_memory_gigabyte_hours,
        0 as cluster_capacity_cpu_core_hours,
        0 as cluster_capacity_memory_gigabyte_hours,
        0 as persistentvolumeclaim_capacity_gigabyte,
        0 as persistentvolumeclaim_capacity_gigabyte_months,
        0 as volume_request_storage_gigabyte_months,
        0 as persistentvolumeclaim_usage_gigabyte_months
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p AS ocp_gcp
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_gcp.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_gcp.usage_start)  = date(rp.report_period_start)
    WHERE ocp_gcp.usage_start >= date('{{start_date | sqlsafe}}')
        AND ocp_gcp.usage_start <= date('{{end_date | sqlsafe}}')
        AND ocp_gcp.report_period_id = {{report_period_id | sqlsafe}}
    GROUP BY ocp_gcp.report_period_id,
        ocp_gcp.usage_start,
        ocp_gcp.cluster_id,
        ocp_gcp.cluster_alias,
        ocp_gcp.namespace,
        ocp_gcp.data_source,
        ocp_gcp.node,
        ocp_gcp.persistentvolumeclaim,
        ocp_gcp.resource_id,
        ocp_gcp.pod_labels,
        rp.provider_id
;
