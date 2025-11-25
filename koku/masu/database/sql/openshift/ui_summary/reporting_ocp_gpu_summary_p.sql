DELETE FROM {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p (
    id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    pod,
    usage_start,
    usage_end,
    vendor_name,
    model_name,
    memory_capacity_mib,
    pod_usage_gpu_hours,
    gpu_count,
    cost_model_gpu_cost,
    source_uuid,
    cost_category_id,
    raw_currency,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_rate_type
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        namespace,
        node,
        max(all_labels->>'pod-name') as pod,
        usage_start,
        usage_start as usage_end,
        max(all_labels->>'gpu-vendor') as vendor_name,
        max(all_labels->>'gpu-model') as model_name,
        max((all_labels->>'gpu-memory-mib')::numeric) as memory_capacity_mib,
        sum((all_labels->>'gpu-uptime-hours')::numeric) as pod_usage_gpu_hours,
        count(DISTINCT resource_id) as gpu_count,
        sum(cost_model_gpu_cost) as cost_model_gpu_cost,
        source_uuid,
        cost_category_id,
        max(raw_currency) as raw_currency,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        max(cost_model_rate_type) as cost_model_rate_type
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE data_source = 'GPU'
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY cluster_id,
        cluster_alias,
        namespace,
        node,
        resource_id,
        usage_start,
        source_uuid,
        cost_category_id
;
