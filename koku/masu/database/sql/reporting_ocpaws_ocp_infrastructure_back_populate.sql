
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
    infrastructure_project_raw_cost,
    infrastructure_usage_cost,
    supplementary_usage_cost,
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
        ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        max(ocp_aws.persistentvolume),
        max(ocp_aws.storageclass),
        ocp_aws.resource_id,
        CASE WHEN ocp_aws.data_source = 'Pod'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_aws.data_source = 'Storage'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        ocp_aws.pod_labels as all_labels,
        rp.provider_id as source_uuid,
        sum(calculated_amortized_cost + markup_cost_amortized) AS infrastructure_raw_cost,
        sum(calculated_amortized_cost + markup_cost_amortized) AS infrastructure_project_raw_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as infrastructure_usage_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as supplementary_usage_cost,
        CASE
            WHEN upper(data_transfer_direction) = 'IN' THEN sum(infrastructure_data_in_gigabytes)
            ELSE NULL
        END as infrastructure_data_in_gigabytes,
        CASE
            WHEN upper(data_transfer_direction) = 'OUT' THEN sum(infrastructure_data_out_gigabytes)
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
        max(ocp_aws.currency_code) as raw_currency,
        max(ocp_aws.cost_category_id) as cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p AS ocp_aws
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_aws.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_aws.usage_start)::date  = date(rp.report_period_start)
    WHERE ocp_aws.usage_start >= {{start_date}}::date
        AND ocp_aws.usage_start <= {{end_date}}::date
        AND ocp_aws.report_period_id = {{report_period_id | sqlsafe}}
    GROUP BY ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        ocp_aws.resource_id,
        ocp_aws.pod_labels,
        ocp_aws.data_transfer_direction,
        rp.provider_id
;
