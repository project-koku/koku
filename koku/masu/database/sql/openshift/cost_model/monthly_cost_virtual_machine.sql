DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.cost_model_rate_type = {{rate_type}}
    AND lids.monthly_cost_type = {{cost_type}}
    AND lids.pod_labels ? 'vm_kubevirt_io_name'
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels,
    all_labels,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
)
WITH cte_cluster_vms AS (
    SELECT cluster_id, 
        namespace,
        COUNT(DISTINCT all_labels->>'vm_kubevirt_io_name') AS vm_count
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS cvms
    WHERE cvms.all_labels ? 'vm_kubevirt_io_name'
        AND cvms.pod_request_cpu_core_hours IS NOT NULL
        AND cvms.pod_request_cpu_core_hours != 0
        AND cvms.report_period_id = {{report_period_id}}
        AND cvms.usage_start >= {{start_date}}::date
        AND cvms.usage_start <= {{end_date}}::date
    GROUP BY cvms.cluster_id, cvms.namespace
)
SELECT uuid_generate_v4(),
    max(report_period_id) as report_period_id,
    lids.cluster_id,
    cluster_alias,
    'Pod' as data_source,
    usage_start,
    usage_end,
    lids.namespace,
    node,
    max(resource_id) as resource_id,
    pod_labels,
    all_labels,
    max(pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    max(pod_request_cpu_core_hours) AS pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    max(pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    max(pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    NULL as node_capacity_cpu_cores,
    NULL as node_capacity_cpu_core_hours,
    NULL as node_capacity_memory_gigabytes,
    NULL as node_capacity_memory_gigabyte_hours,
    NULL as cluster_capacity_cpu_core_hours,
    NULL as cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    {{rate_type}} as cost_model_rate_type,
    CASE
        WHEN {{cost_type}} = 'OCP_VM' AND {{distribution}} = 'cpu'
            THEN {{rate}}::decimal * max(ocp_vms.vm_count)
        WHEN {{cost_type}} = 'OCP_VM_Core_Month' AND {{distribution}} = 'cpu'
                THEN {{rate}}::decimal * sum(lids.pod_request_cpu_core_hours)
        ELSE 0
    END AS cost_model_cpu_cost,
    CASE
        WHEN {{cost_type}} = 'OCP_VM' AND {{distribution}} = 'memory'
            THEN {{rate}}::decimal * max(ocp_vms.vm_count)
        WHEN {{cost_type}} = 'OCP_VM_Core_Month' AND {{distribution}} = 'memory'
                THEN {{rate}}::decimal * sum(lids.pod_request_memory_gigabyte_hours)
        ELSE 0
    END AS cost_model_memory_cost,
    0 as cost_model_volume_cost,
    {{cost_type}} as monthly_cost_type,
    lids.cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_cluster_vms AS ocp_vms
    ON lids.cluster_id = ocp_vms.cluster_id
        AND lids.namespace = ocp_vms.namespace
WHERE lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND all_labels ? 'vm_kubevirt_io_name'
    AND monthly_cost_type IS NULL
GROUP BY usage_start, usage_end, source_uuid, lids.cluster_id, cluster_alias, node, lids.namespace, cost_category_id, pod_labels, all_labels
;
