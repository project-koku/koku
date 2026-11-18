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
    source_uuid,
    cost_model_rate_type,
    distributed_cost
)
WITH unattributed_gpu_cost as (
    SELECT
        cost_model_gpu_cost as gpu_unallocated_cost,
        node,
        all_labels->>'gpu-model' AS gpu_model,
        usage_start,
        cluster_alias,
        cluster_id,
        report_period_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = {{source_uuid}}::uuid
),
namespace_usage_information as (
    -- MIG-aware distribution: use slice-hours instead of just uptime
    -- slice_hours = sum(uptime * slice_count)
    -- This scales the distribution weight by the number of slices each namespace uses
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        sum(gpu_pod_uptime * COALESCE(gpu_usage.mig_slice_count, 1)) as pod_usage_slice_hours,
        gpu_usage.usage_start
    FROM {{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily as gpu_usage
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
      AND gpu_usage.usage_start >= DATE({{start_date}})
      AND gpu_usage.usage_start <= DATE({{end_date}})
    group by gpu_model_name, gpu_usage.node, namespace, gpu_usage.usage_start
),
total_usage as (
    -- Total slice-hours per node/model/date for distribution weighting
    SELECT node, gpu_model_name, usage_start,
           sum(pod_usage_slice_hours) as total_slice_hours
    FROM namespace_usage_information
    GROUP BY node, gpu_model_name, usage_start
)
SELECT
    uuid_generate_v4(),
    max(unattributed.report_period_id) as report_period_id,
    max(unattributed.cluster_id),
    max(unattributed.cluster_alias) as cluster_alias,
    'GPU' as data_source,
    nsp_usage.usage_start,
    nsp_usage.usage_start as usage_end,
    nsp_usage.namespace,
    nsp_usage.node,
    {{source_uuid}}::uuid,
    {{cost_model_rate_type}},
    -- Distribute using slice-hours ratio: namespace_slice_hours / total_slice_hours * unallocated_cost
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
    uuid_generate_v4(),
    unalloc.report_period_id,
    unalloc.cluster_id,
    unalloc.cluster_alias,
    'GPU' as data_source,
    unalloc.usage_start as usage_start,
    unalloc.usage_start as usage_end,
    unalloc.namespace,
    unalloc.node,
    {{source_uuid}}::uuid,
    {{cost_model_rate_type}},
    0 - unalloc.cost_model_gpu_cost as distributed_cost
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as unalloc
WHERE unalloc.namespace = 'GPU unallocated'
    AND unalloc.data_source = 'GPU'
    AND unalloc.usage_start >= DATE({{start_date}})
    AND unalloc.usage_start <= DATE({{end_date}})
    AND unalloc.source_uuid = {{source_uuid}}::uuid
    -- Only zero out if there was namespace usage to distribute to
    AND EXISTS (
        SELECT 1 FROM {{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily as gpu
        WHERE gpu.node = unalloc.node
          AND gpu.gpu_model_name = unalloc.all_labels->>'gpu-model'
          AND gpu.usage_start = unalloc.usage_start
          AND gpu.source = {{source_uuid}}
    )
RETURNING 1;
