DELETE FROM {{schema | sqlsafe}}.reporting_ocp_gpu_summary_by_project_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_gpu_summary_by_project_p (
    id,
    cluster_id,
    cluster_alias,
    namespace,
    usage_start,
    usage_end,
    gpu_vendor_name,
    gpu_model_name,
    gpu_memory_capacity_mib,
    gpu_cost,
    unallocated_gpu_cost,
    source_uuid,
    cost_category_id,
    raw_currency,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_rate_type,
    report_period_id
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        namespace,
        usage_start,
        usage_start as usage_end,
        max(all_labels->>'gpu-vendor') as gpu_vendor_name,
        max(all_labels->>'gpu-model') as gpu_model_name,
        max((all_labels->>'gpu-memory-mib')::numeric) as gpu_memory_capacity_mib,
        sum(cost_model_gpu_cost) as gpu_cost,
        NULL as unallocated_gpu_cost,
        source_uuid,
        cost_category_id,
        max(raw_currency) as raw_currency,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        max(cost_model_rate_type) as cost_model_rate_type,
        report_period_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE data_source = 'GPU'
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY cluster_id,
        cluster_alias,
        namespace,
        usage_start,
        source_uuid,
        cost_category_id,
        report_period_id
;
