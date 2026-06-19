-- Per-rate GPU unallocated cost distribution via rates_to_usage (Trino/SaaS).
-- Reads per-rate GPU costs from RTU (GPU unallocated namespace), distributes
-- proportionally by MIG-aware slice-hours, writes distributed rows back to RTU
-- with monthly_cost_type = 'gpu_distributed'.
INSERT INTO postgres.{{schema | sqlsafe}}.rates_to_usage (
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
    FROM postgres.{{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= DATE({{start_date}})
        AND rtu.usage_start <= DATE({{end_date}})
        AND rtu.source_uuid = CAST({{source_uuid}} AS UUID)
        AND rtu.namespace = 'GPU unallocated'
        AND rtu.monthly_cost_type IS NULL
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id, rtu.cluster_alias,
             rtu.report_period_id, rtu.node,
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
gpu_model_map AS (
    SELECT
        node,
        json_extract_scalar(all_labels, '$["gpu-model"]') AS gpu_model,
        usage_start
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = CAST({{source_uuid}} AS UUID)
    GROUP BY node, json_extract_scalar(all_labels, '$["gpu-model"]'), usage_start
),
namespace_usage_information AS (
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        SUM(gpu_pod_uptime * COALESCE(gpu_usage.mig_slice_count, 1)) AS pod_usage_slice_hours,
        DATE(interval_start) AS usage_start
    FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu_usage
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
      AND DATE(interval_start) >= DATE({{start_date}})
      AND DATE(interval_start) <= DATE({{end_date}})
    GROUP BY gpu_model_name, gpu_usage.node, namespace, DATE(interval_start)
),
total_usage AS (
    SELECT node, gpu_model_name, usage_start,
           SUM(pod_usage_slice_hours) AS total_slice_hours
    FROM namespace_usage_information
    GROUP BY node, gpu_model_name, usage_start
)
SELECT
    uuid(),
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
    {{cost_model_rate_type}},
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
HAVING MAX(nsp.pod_usage_slice_hours / NULLIF(tu.total_slice_hours, 0) * gc.rate_cost) != 0;

-- Negate source: offset GPU unallocated costs so the net distributed total is zero.
INSERT INTO postgres.{{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace,
    cost_model_rate_type,
    monthly_cost_type, distributed_cost
)
SELECT
    uuid(),
    rtu.report_period_id,
    rtu.source_uuid,
    rtu.usage_start,
    rtu.usage_start,
    rtu.cluster_id,
    MAX(rtu.cluster_alias),
    'GPU unallocated',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -SUM(COALESCE(rtu.calculated_cost, 0))
FROM postgres.{{schema | sqlsafe}}.rates_to_usage rtu
WHERE rtu.usage_start >= DATE({{start_date}})
    AND rtu.usage_start <= DATE({{end_date}})
    AND rtu.source_uuid = CAST({{source_uuid}} AS UUID)
    AND rtu.namespace = 'GPU unallocated'
    AND rtu.monthly_cost_type IS NULL
GROUP BY rtu.report_period_id, rtu.source_uuid, rtu.usage_start,
         rtu.cluster_id
HAVING SUM(COALESCE(rtu.calculated_cost, 0)) != 0;
