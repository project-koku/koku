INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocp_gpu_summary_p (
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
    -- gpu_count,
    mig_instance_id,
    physical_gpu_uuid,
    gpu_mode,
    mig_profile,
    mig_slice_count,
    gpu_max_slices,
    mig_strategy,
    mig_memory_capacity_gb,
    source_uuid,
    cost_category_id
)
SELECT uuid(),
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    date(gpu.interval_start) as usage_start,
    date(gpu.interval_start) as usage_end,
    gpu.namespace,
    gpu.node,
    gpu.gpu_vendor_name,
    gpu.gpu_model_name,
    max(gpu.gpu_memory_capacity_mib) * 0.001048576 as memory_capacity_gb,
    -- count(DISTINCT COALESCE(gpu.mig_instance_id, gpu.gpu_uuid)) as gpu_count,
    max(gpu.mig_instance_id) as mig_instance_id,
    max(gpu.gpu_uuid) as physical_gpu_uuid,
    CASE WHEN max(gpu.mig_profile) IS NOT NULL THEN 'MIG' ELSE 'dedicated' END as gpu_mode,
    max(gpu.mig_profile) as mig_profile,
    CAST(max(gpu.mig_slice_count) AS INTEGER) as mig_slice_count,
    CAST(max(gpu.gpu_max_slices) AS INTEGER) as gpu_max_slices,
    max(gpu.mig_strategy) as mig_strategy,
    max(gpu.mig_memory_capacity_mib) * 0.001048576 as mig_memory_capacity_gb,
    cast({{source_uuid}} as UUID),
    max(cat_ns.cost_category_id)
FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON gpu.namespace LIKE cat_ns.namespace
WHERE gpu.source = {{source_uuid}}
    AND gpu.year = {{year}}
    AND lpad(gpu.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND date(gpu.interval_start) >= date({{start_date}})
    AND date(gpu.interval_start) <= date({{end_date}})
GROUP BY gpu.namespace, gpu.node, gpu.gpu_vendor_name, gpu.gpu_model_name, gpu.mig_profile, gpu.interval_start
