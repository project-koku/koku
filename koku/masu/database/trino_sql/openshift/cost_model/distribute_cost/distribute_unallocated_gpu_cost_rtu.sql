-- Per-rate GPU unallocated cost distribution via rates_to_usage (Trino/SaaS).
-- Reads per-rate GPU costs from RTU (GPU unallocated namespace), distributes
-- proportionally by MIG-aware slice-hours, writes distributed rows back to RTU
-- with monthly_cost_type = 'gpu_distributed'.
INSERT INTO postgres.{{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost, cost_model_id
)
WITH gpu_rtu_cost AS (
    SELECT
        rtu.usage_start,
        rtu.source_uuid,
        rtu.cluster_id,
        rtu.cluster_alias,
        rtu.report_period_id,
        rtu.node,
        json_extract_scalar(rtu.all_labels, '$["gpu-model"]') AS gpu_model,
        rtu.custom_name,
        rtu.metric_type,
        rtu.cost_model_rate_type,
        SUM(COALESCE(rtu.calculated_cost, CAST(0 AS DECIMAL))) AS rate_cost
    FROM postgres.{{schema | sqlsafe}}.rates_to_usage rtu
    WHERE rtu.usage_start >= DATE({{start_date}})
        AND rtu.usage_start <= DATE({{end_date}})
        AND rtu.source_uuid = CAST({{source_uuid}} AS UUID)
        AND rtu.namespace = 'GPU unallocated'
        AND (rtu.monthly_cost_type IS NULL OR rtu.monthly_cost_type NOT IN (
            'worker_distributed', 'platform_distributed', 'gpu_distributed',
            'unattributed_storage', 'unattributed_network'
        ))
    -- Grouping by gpu-model keeps each model's cost isolated so it is only
    -- distributed among the usage rows for that same model (see namespace_usage_information).
    -- Without this, a node with multiple GPU models would have its combined cost
    -- re-applied in full once per model, over-distributing to real namespaces.
    GROUP BY rtu.usage_start, rtu.source_uuid, rtu.cluster_id, rtu.cluster_alias,
             rtu.report_period_id, rtu.node, json_extract_scalar(rtu.all_labels, '$["gpu-model"]'),
             rtu.custom_name, rtu.metric_type, rtu.cost_model_rate_type
),
namespace_usage_information AS (
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        SUM(gpu_pod_uptime * COALESCE(gpu_usage.mig_slice_count, 1)) AS pod_usage_slice_hours,
        DATE(interval_start) AS usage_start
    FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu_usage
    WHERE source = {{source_uuid | string}}
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
    COALESCE(gc.custom_name, ''),
    gc.metric_type,
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -- SUM (not MAX): a namespace can have usage on more than one GPU model on the
    -- same node, and each model's contribution must accumulate into one output row.
    SUM(nsp.pod_usage_slice_hours / NULLIF(tu.total_slice_hours, 0) * gc.rate_cost),
    CAST({{cost_model_id}} AS UUID)
FROM gpu_rtu_cost gc
JOIN namespace_usage_information nsp
    ON nsp.node = gc.node
    AND nsp.gpu_model_name = gc.gpu_model
    AND nsp.usage_start = gc.usage_start
JOIN total_usage tu
    ON tu.node = nsp.node
    AND tu.gpu_model_name = nsp.gpu_model_name
    AND tu.usage_start = nsp.usage_start
GROUP BY nsp.usage_start, nsp.node, nsp.namespace,
         gc.source_uuid, gc.custom_name, gc.metric_type, gc.cost_model_rate_type
HAVING SUM(nsp.pod_usage_slice_hours / NULLIF(tu.total_slice_hours, 0) * gc.rate_cost) != 0;

-- Negate source: derive negation from the distributed output rows just inserted.
-- Sums distributed_cost of gpu_distributed rows and inserts exact negative,
-- guaranteeing algebraic zero-sum.
INSERT INTO postgres.{{schema | sqlsafe}}.rates_to_usage (
    uuid, report_period_id, source_uuid, usage_start, usage_end,
    cluster_id, cluster_alias, namespace, node,
    custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, distributed_cost, cost_model_id
)
SELECT
    uuid(),
    MAX(rtu.report_period_id),
    rtu.source_uuid,
    rtu.usage_start,
    rtu.usage_start,
    rtu.cluster_id,
    MAX(rtu.cluster_alias),
    'GPU unallocated',
    rtu.node,
    '', '',
    {{cost_model_rate_type}},
    {{cost_model_rate_type}},
    -SUM(rtu.distributed_cost),
    CAST({{cost_model_id}} AS UUID)
FROM postgres.{{schema | sqlsafe}}.rates_to_usage rtu
WHERE rtu.usage_start >= DATE({{start_date}})
    AND rtu.usage_start <= DATE({{end_date}})
    AND rtu.source_uuid = CAST({{source_uuid}} AS UUID)
    AND rtu.monthly_cost_type = {{cost_model_rate_type}}
    AND rtu.namespace != 'GPU unallocated'
GROUP BY rtu.source_uuid, rtu.usage_start, rtu.cluster_id, rtu.node
HAVING SUM(rtu.distributed_cost) != CAST(0 AS DECIMAL);
