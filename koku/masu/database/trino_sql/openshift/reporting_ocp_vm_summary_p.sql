INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
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
    infrastructure_markup_cost,
    infrastructure_raw_cost,
    raw_currency,
    resource_ids,
    usage_start,
    usage_end,
    cost_category_id,
    source_uuid,
    persistentvolumeclaim,
    persistentvolumeclaim_capacity_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    storageclass
)
with cte_vm_names as (
    select
        vm_name,
        CONCAT('vm_kubevirt_io_name": "', vm_name) as substring
    from postgres.{{schema | sqlsafe}}.reporting_ocp_vm_summary_p
    WHERE usage_start >= DATE({{start_date}})
        AND usage_start <= date({{end_date}})
        AND source_uuid = {{source_uuid}}
    group by vm_name
),
cte_persistent_storage_info as (
    SELECT
        storage.persistentvolumeclaim,
        storage.pod,
        pod_usage.vm_name
    FROM openshift_storage_usage_line_items_daily storage
    JOIN (
            SELECT
                pod,
                vm.vm_name
            FROM openshift_pod_usage_line_items_daily
            JOIN cte_vm_names as vm
                ON strpos(lower(pod_labels), vm.substring) != 0
            WHERE pod_labels IS NOT NULL
                AND pod_labels != ''
                AND source = CAST({{source_uuid}} as varchar)
                AND month = {{month}}
                AND year = {{year}}
            GROUP BY pod, vm.vm_name
        ) pod_usage
    ON storage.pod = pod_usage.pod
    WHERE storage.month = {{month}}
        AND storage.year = {{year}}
        AND storage.source = CAST({{source_uuid}} as varchar)
    GROUP BY storage.persistentvolumeclaim, storage.pod, pod_usage.vm_name
)
SELECT uuid() as id,
    cluster_alias,
    cluster_id,
    namespace,
    max(ocp.node) as node,
    storage.vm_name as vm_name,
    sum(cost_model_cpu_cost) as cost_model_cpu_cost,
    sum(cost_model_memory_cost) as cost_model_memory_cost,
    cost_model_rate_type,
    sum(cost_model_volume_cost) as cost_model_volume_cost,
    sum(distributed_cost) as distributed_cost,
    sum(infrastructure_markup_cost) as infrastructure_markup_cost,
    sum(infrastructure_raw_cost) as infrastructure_raw_cost,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(usage_start) as usage_start,
    max(usage_start) as usage_end,
    max(cost_category_id) as cost_category_id,
    {{source_uuid}} as source_uuid,
    max(ocp.persistentvolumeclaim) as persistentvolumeclaim,
    max(ocp.persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
    max(ocp.persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
    max(ocp.storageclass) as storageclass
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
INNER JOIN cte_persistent_storage_info as storage
    ON storage.persistentvolumeclaim = ocp.persistentvolumeclaim
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND source_uuid = {{source_uuid}}
    AND data_source = 'Storage'
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
GROUP BY cluster_alias, cluster_id, namespace, vm_name, cost_model_rate_type, ocp.persistentvolumeclaim
