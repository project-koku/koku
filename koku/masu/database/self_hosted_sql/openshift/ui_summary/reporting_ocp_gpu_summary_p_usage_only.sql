DELETE FROM {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}::uuid
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p (
    id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    node,
    vendor_name,
    model_name,
    memory_capacity_gb,
    gpu_count,
    mig_instance_id,
    gpu_uuid,
    gpu_mode,
    mig_profile,
    mig_slice_count,
    gpu_max_slices,
    mig_strategy,
    mig_memory_capacity_gb,
    source_uuid,
    cost_category_id
)
SELECT uuid_generate_v4(),
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    gpu.usage_start,
    gpu.usage_start as usage_end,
    gpu.namespace,
    gpu.node,
    gpu.gpu_vendor_name,
    gpu.gpu_model_name,
    max(gpu.gpu_memory_capacity_mib) * 0.001048576 as memory_capacity_gb,
    count(DISTINCT COALESCE(gpu.mig_instance_id, gpu.gpu_uuid)) as gpu_count,
    max(gpu.mig_instance_id) as mig_instance_id,
    max(gpu.gpu_uuid) as gpu_uuid,
    CASE WHEN max(NULLIF(gpu.mig_profile, '')) IS NOT NULL THEN 'MIG' ELSE 'dedicated' END as gpu_mode,
    max(NULLIF(gpu.mig_profile, '')) as mig_profile,
    max(gpu.mig_slice_count) as mig_slice_count,
    max(gpu.gpu_max_slices) as gpu_max_slices,
    max(gpu.mig_strategy) as mig_strategy,
    max(gpu.mig_memory_capacity_mib) * 0.001048576 as mig_memory_capacity_gb,
    {{source_uuid}}::uuid,
    max(cat_ns.cost_category_id)
FROM {{schema | sqlsafe}}.openshift_gpu_usage_line_items AS gpu
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON gpu.namespace LIKE cat_ns.namespace
WHERE gpu.source = {{source_uuid}}
    AND gpu.year = {{year}}
    AND lpad(gpu.month, 2, '0') = {{month}}
    AND gpu.usage_start >= date({{start_date}})
    AND gpu.usage_start <= date({{end_date}})
GROUP BY gpu.namespace, gpu.node, gpu.gpu_vendor_name, gpu.gpu_model_name, gpu.mig_profile, gpu.usage_start, gpu.mig_instance_id, gpu.gpu_uuid
RETURNING 1;
