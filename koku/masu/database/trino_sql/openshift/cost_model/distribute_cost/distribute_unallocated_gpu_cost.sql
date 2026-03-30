INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    source_uuid,
    cost_model_rate_type,
    distributed_cost
)
WITH unattributed_gpu_cost as (
    SELECT
        cost_model_gpu_cost as gpu_unallocated_cost,
        node,
        json_extract_scalar(all_labels, '$["gpu-model"]') AS gpu_model,
        usage_start,
        cluster_alias,
        cluster_id,
        report_period_id
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = CAST({{source_uuid}} AS UUID)
),
namespace_usage_information as (
    -- MIG-aware distribution: use slice-hours instead of just uptime
    -- slice_hours = sum(uptime * slice_count)
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        sum(gpu_pod_uptime * COALESCE(gpu_usage.mig_slice_count, 1)) as pod_usage_slice_hours,
        DATE(interval_start) as usage_start
    FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, gpu_usage.node, namespace, DATE(interval_start)
),
total_usage as (
    SELECT node, gpu_model_name, usage_start,
           sum(pod_usage_slice_hours) as total_slice_hours
    FROM namespace_usage_information
    GROUP BY node, gpu_model_name, usage_start
)
SELECT
    uuid(),
    max(unattributed.report_period_id) as report_period_id,
    max(unattributed.cluster_id),
    max(unattributed.cluster_alias) as cluster_alias,
    'GPU' as data_source,
    nsp_usage.usage_start,
    nsp_usage.usage_start as usage_end,
    nsp_usage.namespace,
    nsp_usage.node,
    CAST({{source_uuid}} AS UUID),
    {{cost_model_rate_type}},
    max(nsp_usage.pod_usage_slice_hours / NULLIF(total_usage.total_slice_hours, 0) * unattributed.gpu_unallocated_cost) as distributed_cost
FROM namespace_usage_information as nsp_usage
JOIN unattributed_gpu_cost as unattributed
    ON unattributed.node = nsp_usage.node
    AND unattributed.gpu_model = nsp_usage.gpu_model_name
    AND unattributed.usage_start = nsp_usage.usage_start
JOIN total_usage
    ON total_usage.node = nsp_usage.node
    AND total_usage.gpu_model_name = nsp_usage.gpu_model_name
    AND total_usage.usage_start = nsp_usage.usage_start
GROUP BY nsp_usage.usage_start, nsp_usage.node, nsp_usage.namespace

UNION

SELECT
    uuid(),
    report_period_id,
    cluster_id,
    cluster_alias,
    'GPU' as data_source,
    usage_start as usage_start,
    usage_start as usage_end,
    namespace,
    node,
    CAST({{source_uuid}} AS UUID),
    {{cost_model_rate_type}},
    0 - cost_model_gpu_cost as distributed_cost
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE namespace = 'GPU unallocated'
    AND usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND source_uuid = CAST({{source_uuid}} AS UUID);
