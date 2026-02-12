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
        sum(cost_model_gpu_cost) as gpu_unallocated_cost,
        node,
        all_labels::jsonb->>'gpu-model' AS gpu_model,
        cluster_alias,
        cluster_id,
        report_period_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE namespace = 'GPU unallocated'
      AND usage_start >= DATE({{start_date}})
      AND usage_start <= DATE({{end_date}})
      AND source_uuid = {{source_uuid}}::uuid
    GROUP BY node, 3, cluster_alias, cluster_id, report_period_id
),
namespace_usage_information as (
    SELECT gpu_model_name,
        gpu_usage.namespace,
        gpu_usage.node,
        sum(gpu_pod_uptime) as pod_usage_uptime,
        gpu_usage.usage_start
    FROM {{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily as gpu_usage
    INNER JOIN unattributed_gpu_cost AS ungpu
        ON ungpu.node = gpu_usage.node
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    group by gpu_model_name, gpu_usage.node, namespace, gpu_usage.usage_start
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
    max(nsp_usage.pod_usage_uptime / total_usage.total_pod_uptime * unattributed.gpu_unallocated_cost) as distributed_cost
FROM namespace_usage_information as nsp_usage
JOIN unattributed_gpu_cost as unattributed
    ON unattributed.node = nsp_usage.node
JOIN (
    SELECT sum(pod_usage_uptime) as total_pod_uptime, node FROM namespace_usage_information group by node
) as total_usage
    ON unattributed.node = total_usage.node
GROUP BY nsp_usage.usage_start, nsp_usage.node, nsp_usage.namespace

UNION

SELECT
    uuid_generate_v4(),
    report_period_id,
    cluster_id,
    cluster_alias,
    'GPU' as data_source,
    usage_start as usage_start,
    usage_start as usage_end,
    namespace,
    node,
    {{source_uuid}}::uuid,
    {{cost_model_rate_type}},
    0 - cost_model_gpu_cost as distributed_cost
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE namespace = 'GPU unallocated'
    AND usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND source_uuid = {{source_uuid}}::uuid
RETURNING 1;
