INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocp_gpu_summary_p (
    id,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    pod,
    usage_start,
    usage_end,
    gpu_vendor_name,
    gpu_model_name,
    gpu_memory_capacity_mib,
    gpu_pod_uptime,
    gpu_count,
    source_uuid
)
SELECT uuid() as id,
       {{report_period_id}} as report_period_id,
       {{cluster_id}} as cluster_id,
       {{cluster_alias}} as cluster_alias,
       namespace,
       node,
       pod,
       CAST(interval_start AS date) as usage_start,
       CAST(interval_start AS date) as usage_end,
       gpu_vendor_name,
       gpu_model_name,
       MAX(gpu_memory_capacity_mib) as gpu_memory_capacity_mib,
       SUM(gpu_pod_uptime) as gpu_pod_uptime,
       COUNT(DISTINCT gpu_uuid) as gpu_count,
       CAST({{source_uuid}} AS uuid) as source_uuid
FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily
WHERE source = {{source_uuid | string}}
  AND year = {{year}}
  AND month = {{month}}
GROUP BY namespace, node, pod, CAST(interval_start AS date),
         gpu_vendor_name, gpu_model_name
;
