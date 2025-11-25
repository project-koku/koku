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
        json_extract_scalar(all_labels, '$["gpu-model"]') AS gpu_model
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = {{source_uuid}}
    GROUP BY node, 3
),
namespace_usage_information as (
    SELECT gpu_model_name,
        namespace,
        sum(gpu_pod_uptime) as namespace_gpu_pod_uptime
    FROM openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, namespace
),
node_usage_information as (
    SELECT gpu_model_name,
        node,
        sum(gpu_pod_uptime) as node_gpu_pod_uptime
    FROM openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, node
)
SELECT
    uuid()
    max(report_period_id) as report_period_id,
    cluster_id,
    cluster_alias as cluster_alias,
    filtered.data_source as data_source,
    filtered.usage_start,
    max(usage_end) as usage_end,
    filtered.namespace,
    filtered.node,
    max(resource_id) as resource_id,
    CASE WHEN namespace != 'GPU unallocated' THEN
        x.namespace_gpu_pod_uptime / y.node_gpu_pod_uptime * z.unattributed_gpu_cost as cost_model_gpu_cost
    WHEN namespace != 'GPU unallocated' THEN
    0 - SUM(COALESCE(cost_model_gpu_cost, 0))
    END as distributed_cost,
    max(cost_category_id) as cost_category_id,
    max(raw_currency) as raw_currency
FROM xyz
WHERE filtered.namespace IS NOT NULL
GROUP BY filtered.usage_start, filtered.node, filtered.namespace, filtered.cluster_id, filtered.cost_category_id, filtered.data_source;
