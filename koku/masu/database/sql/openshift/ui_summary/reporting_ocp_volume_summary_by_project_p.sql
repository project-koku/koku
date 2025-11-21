DELETE FROM {{schema | sqlsafe}}.reporting_ocp_volume_summary_by_project_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_volume_summary_by_project_p (
    id,
    cluster_id,
    cluster_alias,
    namespace,
    resource_ids,
    resource_count,
    data_source,
    usage_start,
    usage_end,
    infrastructure_raw_cost,
    infrastructure_markup_cost,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_gpu_cost,
    cost_model_rate_type,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    persistentvolumeclaim_capacity_gigabyte_months,
    source_uuid,
    cost_category_id,
    raw_currency,
    distributed_cost,
    persistentvolumeclaim,
    storageclass
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        namespace,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        max(data_source) as data_source,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        sum(cost_model_gpu_cost) as cost_model_gpu_cost,
        cost_model_rate_type,
        sum(volume_request_storage_gigabyte_months) as volume_request_storage_gigabyte_months,
        sum(persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months,
        sum(persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
        {{source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id,
        max(raw_currency) as raw_currency,
        sum(distributed_cost) as distributed_cost,
        persistentvolumeclaim,
        storageclass
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Storage'
        AND persistentvolumeclaim IS NOT NULL
    GROUP BY usage_start, cluster_id, cluster_alias, namespace, cost_model_rate_type, persistentvolumeclaim, storageclass
;
