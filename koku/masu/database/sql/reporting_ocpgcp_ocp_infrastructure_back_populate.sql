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
    cost_category_id,
    source_uuid,
    infrastructure_raw_cost,
    infrastructure_project_raw_cost,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
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
    persistentvolumeclaim_usage_gigabyte_months,
    raw_currency
)
    SELECT uuid_generate_v4() as uuid,
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
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_gcp.data_source = 'Storage'
            THEN ocp_gcp.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        ocp_gcp.pod_labels as all_labels,
        max(ocp_gcp.cost_category_id) as cost_category_id,
        rp.provider_id as source_uuid,
        sum(
            coalesce(ocp_gcp.unblended_cost, 0)
            + coalesce(ocp_gcp.markup_cost, 0)
            + coalesce(ocp_gcp.credit_amount, 0)
        ) AS infrastructure_raw_cost,
        sum(
            coalesce(ocp_gcp.unblended_cost ,0)
            + coalesce(ocp_gcp.markup_cost, 0)
            + coalesce(ocp_gcp.credit_amount, 0)
        ) AS infrastructure_project_raw_cost,
        CASE
            WHEN upper(data_transfer_direction) = 'IN' THEN sum(infrastructure_data_in_gigabytes)
            ELSE NULL
        END as infrastructure_data_in_gigabytes,
        CASE
            WHEN upper(data_transfer_direction) = 'OUT' THEN sum(infrastructure_data_out_gigabytes)
            ELSE NULL
        END as infrastructure_data_out_gigabytes,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as infrastructure_usage_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as supplementary_usage_cost,
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
        max(ocp_gcp.currency) as raw_currency
    FROM {{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p AS ocp_gcp
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_gcp.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_gcp.usage_start)::date = date(rp.report_period_start)
    WHERE ocp_gcp.usage_start >= {{start_date}}::date
        AND ocp_gcp.usage_start <= {{end_date}}::date
        AND ocp_gcp.report_period_id = {{report_period_id}}
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
        ocp_gcp.data_transfer_direction,
        rp.provider_id
;
