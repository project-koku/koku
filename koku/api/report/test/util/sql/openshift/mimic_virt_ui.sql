INSERT INTO {{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
    id,
    cluster_alias,
    cluster_id,
    namespace,
    node,
    vm_name,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_rate_type,
    cost_model_volume_cost,
    distributed_cost,
    pod_labels,
    pod_request_cpu_core_hours,
    pod_request_memory_gigabyte_hours,
    infrastructure_markup_cost,
    infrastructure_raw_cost,
    raw_currency,
    resource_ids,
    usage_start,
    usage_end,
    cost_category_id,
    source_uuid
)
SELECT uuid_generate_v4() as id,
    cluster_alias,
    cluster_id,
    namespace,
    node as node,
    pod_labels->>'vm_kubevirt_io_name' as vm_name,
    sum(cost_model_cpu_cost) as cost_model_cpu_cost,
    sum(cost_model_memory_cost) as cost_model_memory_cost,
    cost_model_rate_type,
    sum(cost_model_volume_cost) as cost_model_volume_cost,
    sum(distributed_cost) as distributed_cost,
    pod_labels as pod_labels,
    {{pod_request_cpu_core_hours}} as pod_request_cpu_core_hours,
    {{pod_request_mem_core_hours}} as pod_request_memory_gigabyte_hours,
    sum(infrastructure_markup_cost) as infrastructure_markup_cost,
    sum(infrastructure_raw_cost) as infrastructure_raw_cost,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(usage_start) as usage_start,
    max(usage_start) as usage_end,
    max(cost_category_id) as cost_category_id,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND data_source = 'Pod'
    AND pod_labels ? 'vm_kubevirt_io_name'
    AND namespace IS DISTINCT FROM 'Worker unallocated'
    AND namespace IS DISTINCT FROM 'Platform unallocated'
    AND namespace IS DISTINCT FROM 'Network unattributed'
    AND namespace IS DISTINCT FROM 'Storage unattributed'
    AND (
        COALESCE(cost_model_cpu_cost, 0)
        + COALESCE(cost_model_memory_cost, 0)
        + COALESCE(cost_model_volume_cost, 0)
        + COALESCE(distributed_cost, 0)
        + COALESCE(infrastructure_raw_cost, 0)
        + COALESCE(infrastructure_markup_cost, 0)) != 0
GROUP BY cluster_alias, cluster_id, namespace, node, vm_name, cost_model_rate_type, pod_labels
;
