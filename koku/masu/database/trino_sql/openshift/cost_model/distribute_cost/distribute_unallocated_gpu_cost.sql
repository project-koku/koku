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
    resource_id,
    all_labels,
    source_uuid,
    monthly_cost_type,
    cost_model_rate_type,
    distributed_cost
)
WITH unattributed_gpu_cost as (
    SELECT
        sum(cost_model_gpu_cost),
        node,
        json_extract_scalar(all_labels, '$["gpu-model"]') AS gpu_model,
        cluster_alias,
        cluster_id,
        report_period_id
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = CAST({{source_uuid}} AS UUID)
    GROUP BY node, 3, cluster_alias, cluster_id, report_period_id
),
namespace_usage_information as (
    SELECT gpu_model_name,
        namespace,
        sum(gpu_pod_uptime) as namespace_gpu_pod_uptime,
        DATE(interval_start) as usage_start
    FROM openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, namespace, DATE(interval_start)
),
node_usage_information as (
    SELECT gpu_model_name,
        ungpu.node,
        sum(gpu_pod_uptime) as node_gpu_pod_uptime,
        DATE(interval_start) AS usage_start
    FROM trino.{{schema | sqlsafe}}openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, ungpu.node, DATE(interval_start)
)
SELECT
    uuid()
    max(unattributed.report_period_id) as report_period_id,
    max(unattributed.cluster_id),
    max(unattributed.cluster_alias) as cluster_alias,
    'GPU' as data_source,
    nsp_usage.usage_start,
    nsp_usage.usage_start as usage_end,
    nsp_usage.namespace,
    node_usage.node,
    NULL as resource_id,
    CASE WHEN namespace != 'GPU unallocated' THEN
        max(nsp_usage.namespace_gpu_pod_uptime / node_usage.node_gpu_pod_uptime * unattributed.gpu_unallocated_cost)
    WHEN namespace != 'GPU unallocated' THEN
    max(0 - (COALESCE(unattributed.gpu_unallocated_cost, 0)))
    END as distributed_cost
FROM node_usage_information as node_usage
JOIN namespace_usage_information as nsp_usage
    ON node_usage.gpu_model_name = nsp_usage.gpu_model_name
    and node_usage.usage_start = nsp_usage.usage_start
JOIN unattributed_gpu_cost as unattributed
    ON unattributed.node = node_usage.node
GROUP BY nsp_usage.usage_start, node_usage.node, nsp_usage.namespace;
