INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
    all_labels,
    source_uuid,
    infrastructure_raw_cost,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
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
    persistentvolumeclaim_usage_gigabyte_months,
    raw_currency,
    cost_category_id
)
    SELECT uuid_generate_v4() as uuid,
        ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.persistentvolumeclaim,
        max(ocp_azure.persistentvolume),
        max(ocp_azure.storageclass),
        ocp_azure.resource_id,
        CASE WHEN ocp_azure.data_source = 'Pod'
            THEN ocp_azure.pod_labels
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_azure.data_source = 'Storage'
            THEN ocp_azure.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        ocp_azure.pod_labels as all_labels,
        rp.provider_id as source_uuid,
        sum(
            coalesce(ocp_azure.pretax_cost, 0)
            + coalesce(ocp_azure.markup_cost, 0)
        ) AS infrastructure_raw_cost,
        CASE
            WHEN data_transfer_direction = 'IN' THEN sum(infrastructure_data_in_gigabytes)
            ELSE NULL
        END as infrastructure_data_in_gigabytes,
        CASE
            WHEN data_transfer_direction = 'OUT' THEN sum(infrastructure_data_out_gigabytes)
            ELSE NULL
        END as infrastructure_data_out_gigabytes,
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
        0 as persistentvolumeclaim_usage_gigabyte_months,
        max(ocp_azure.currency) as raw_currency,
        max(ocp_azure.cost_category_id) as cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_p AS ocp_azure
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_azure.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_azure.usage_start)::date  = date(rp.report_period_start)
    WHERE ocp_azure.usage_start >= {{start_date}}::date
        AND ocp_azure.usage_start <= {{end_date}}::date
        AND ocp_azure.report_period_id = {{report_period_id | sqlsafe}}
    GROUP BY ocp_azure.report_period_id,
        ocp_azure.usage_start,
        ocp_azure.cluster_id,
        ocp_azure.cluster_alias,
        ocp_azure.namespace,
        ocp_azure.data_source,
        ocp_azure.node,
        ocp_azure.persistentvolumeclaim,
        ocp_azure.resource_id,
        ocp_azure.pod_labels,
        ocp_azure.data_transfer_direction,
        rp.provider_id
;
