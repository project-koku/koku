-- When debugging you can add
-- pod_usage.namespace, pod_usage.node, pod_usage.pod, pod_usage.pod_labels,
-- to the storage info select
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
    pod_labels,
    cost_category_id,
    source_uuid,
    persistentvolumeclaim,
    persistentvolumeclaim_capacity_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    storageclass
)
WITH storage_info AS (
    SELECT
        storage.persistentvolumeclaim,
        vm.vm_name
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS pod_usage
    INNER JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as storage
        ON pod_usage.pod = storage.pod
        AND pod_usage.year = storage.year
        AND pod_usage.month = storage.month
        AND pod_usage.source = storage.source
    INNER JOIN (
        select
            vm_name,
            CONCAT('vm_kubevirt_io_name": "', vm_name) as substring
        from postgres.{{schema | sqlsafe}}.reporting_ocp_vm_summary_p
        WHERE usage_start >= DATE({{start_date}})
            AND usage_start <= DATE({{end_date}})
            AND source_uuid = CAST({{source_uuid}} as uuid)
        group by vm_name
    ) vm
        ON strpos(lower(pod_labels), vm.substring) != 0
    WHERE storage.persistentvolumeclaim IS NOT NULL
        AND storage.persistentvolumeclaim != ''
        AND pod_usage.year = {{year}}
        AND pod_usage.month = {{month}}
        AND pod_usage.source = {{source_uuid}}
        AND pod_usage.pod_labels != ''
        AND pod_usage.pod_labels IS NOT NULL
    GROUP BY storage.persistentvolumeclaim, vm_name
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
    all_labels as pod_labels,
    max(cost_category_id) as cost_category_id,
    CAST({{source_uuid}} as uuid) as source_uuid,
    max(ocp.persistentvolumeclaim) as persistentvolumeclaim,
    max(ocp.persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
    max(ocp.persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
    max(ocp.storageclass) as storageclass
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN storage_info AS storage
    ON storage.persistentvolumeclaim = ocp.persistentvolumeclaim
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND source_uuid = CAST({{source_uuid}} as uuid)
    AND data_source = 'Storage'
    AND namespace IS DISTINCT FROM 'Worker unallocated'
    AND namespace IS DISTINCT FROM 'Platform unallocated'
    AND namespace IS DISTINCT FROM 'Network unattributed'
    AND namespace IS DISTINCT FROM 'Storage unattributed'
GROUP BY all_labels, cluster_alias, cluster_id, namespace, vm_name, cost_model_rate_type, ocp.persistentvolumeclaim
