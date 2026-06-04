-- Per-rate GPU unallocated cost distribution via rates_to_usage (self-hosted).
-- Reads per-rate GPU costs from RTU (GPU unallocated namespace), distributes
-- proportionally by MIG-aware slice-hours, writes distributed rows back to RTU
-- with monthly_cost_type = 'gpu_distributed'.
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost
)
WITH gpu_rtu_cost AS (
    SELECT
        rtu.usage_start,
        rtu.source_uuid,
        rtu.cluster_id,
        rtu.cluster_alias,
        rtu.report_period_id,
        rtu.node,
        rtu.custom_name,
        rtu.metric_type,
        rtu.cost_model_rate_type,
        SUM(COALESCE(rtu.calculated_cost, 0)) AS rate_cost
    FROM {{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= DATE({{start_date}})
        AND rtu.usage_start <= DATE({{end_date}})
        AND rtu.source_uuid = {{source_uuid}}::uuid
        AND rtu.namespace = 'GPU unallocated'
        AND rtu.monthly_cost_type IS NULL
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id, rtu.cluster_alias,
             rtu.report_period_id, rtu.node,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
gpu_model_map AS (
    SELECT
        node,
        all_labels->>'gpu-model' AS gpu_model,
        usage_start
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = {{source_uuid}}::uuid
    GROUP BY node, all_labels->>'gpu-model', usage_start
),
namespace_usage_information AS (
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        SUM(gpu_pod_uptime * COALESCE(gpu_usage.mig_slice_count, 1)) AS pod_usage_slice_hours,
        gpu_usage.usage_start
    FROM {{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu_usage
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
      AND gpu_usage.usage_start >= DATE({{start_date}})
      AND gpu_usage.usage_start <= DATE({{end_date}})
    GROUP BY gpu_model_name, gpu_usage.node, namespace, gpu_usage.usage_start
),
total_usage AS (
    SELECT node, gpu_model_name, usage_start,
           SUM(pod_usage_slice_hours) AS total_slice_hours
    FROM namespace_usage_information
    GROUP BY node, gpu_model_name, usage_start
)
SELECT
    uuid_generate_v4(),
    MAX(gc.report_period_id),
    gc.source_uuid,
    nsp.usage_start,
    nsp.usage_start,
    MAX(gc.cluster_id),
    MAX(gc.cluster_alias),
    nsp.namespace,
    nsp.node,
    gc.custom_name,
    gc.metric_type,
    gc.cost_model_rate_type,
    {{cost_model_rate_type}},
    MAX(nsp.pod_usage_slice_hours / NULLIF(tu.total_slice_hours, 0) * gc.rate_cost)
FROM gpu_rtu_cost gc
JOIN gpu_model_map gm
    ON gm.node = gc.node AND gm.usage_start = gc.usage_start
JOIN namespace_usage_information nsp
    ON nsp.node = gc.node
    AND nsp.gpu_model_name = gm.gpu_model
    AND nsp.usage_start = gc.usage_start
JOIN total_usage tu
    ON tu.node = nsp.node
    AND tu.gpu_model_name = nsp.gpu_model_name
    AND tu.usage_start = nsp.usage_start
GROUP BY nsp.usage_start, nsp.node, nsp.namespace,
         gc.source_uuid, gc.custom_name, gc.metric_type, gc.cost_model_rate_type
HAVING MAX(nsp.pod_usage_slice_hours / NULLIF(tu.total_slice_hours, 0) * gc.rate_cost) != 0
RETURNING 1;
