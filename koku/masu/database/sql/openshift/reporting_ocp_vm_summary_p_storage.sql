 INSERT INTO {{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
    id,
    pod_labels,
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
WITH latest_vm_pod_labels as (
    SELECT DISTINCT vm_name, pod_labels from {{schema | sqlsafe}}.reporting_ocp_vm_summary_p
    WHERE pod_labels IS NOT NULL
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
),
second_to_last_day AS (
    SELECT DISTINCT usage_start::date AS day
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND persistentvolumeclaim IS NOT NULL
    ORDER BY day DESC
    OFFSET 1 LIMIT 1  -- Get the second-to-last day
),
latest_storage_data AS (
    SELECT DISTINCT ON (persistentvolumeclaim)
        persistentvolumeclaim,
        CASE
            WHEN volume_labels IS NOT NULL AND vm_labels.pod_labels IS NOT NULL THEN
                jsonb_concat(volume_labels, vm_labels.pod_labels)
            ELSE
                COALESCE(volume_labels, vm_labels.pod_labels)
        END as combined_labels,
        map.vm_name as vm_name
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} AS map
        ON map.pvc_name = ocp.persistentvolumeclaim
    LEFT JOIN latest_vm_pod_labels as vm_labels
        ON map.vm_name = vm_labels.vm_name
    WHERE usage_start::date = (SELECT day FROM second_to_last_day)
        AND persistentvolumeclaim IS NOT NULL
    ORDER BY persistentvolumeclaim, usage_start DESC
)
SELECT uuid_generate_v4() as id,
    storage.combined_labels as  pod_labels,
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
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN latest_storage_data AS storage
    ON storage.persistentvolumeclaim = ocp.persistentvolumeclaim
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
    AND data_source = 'Storage'
    AND namespace IS DISTINCT FROM 'Worker unallocated'
    AND namespace IS DISTINCT FROM 'Platform unallocated'
    AND namespace IS DISTINCT FROM 'Network unattributed'
    AND namespace IS DISTINCT FROM 'Storage unattributed'
GROUP BY storage.combined_labels, cluster_alias, cluster_id, namespace, vm_name, cost_model_rate_type, ocp.persistentvolumeclaim;

DROP TABLE {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}};
