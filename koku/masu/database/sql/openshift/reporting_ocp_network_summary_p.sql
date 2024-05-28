DELETE FROM {{schema | sqlsafe}}.reporting_ocp_network_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

-- One record for data in and another for data out to keep costs separate
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_network_summary_p (
    id,
    cluster_id,
    cluster_alias,
    resource_ids,
    resource_count,
    data_source,
    usage_start,
    usage_end,
    infrastructure_raw_cost,
    infrastructure_markup_cost,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_rate_type,
    source_uuid,
    cost_category_id,
    raw_currency,
    distributed_cost
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        max(data_source) as data_source,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        sum(infrastructure_data_in_gigabytes),
        0 as infrastructure_data_out_gigabytes,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        cost_model_rate_type,
        {{source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id,
        max(raw_currency) as raw_currency,
        sum(distributed_cost) as distributed_cost
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Pod'
        AND namespace = 'Network unattributed'
        AND infrastructure_data_in_gigabytes IS NOT NULL
    GROUP BY usage_start, cluster_id, cluster_alias, cost_model_rate_type
;

-- Data outbound record
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_network_summary_p (
    id,
    cluster_id,
    cluster_alias,
    resource_ids,
    resource_count,
    data_source,
    usage_start,
    usage_end,
    infrastructure_raw_cost,
    infrastructure_markup_cost,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_rate_type,
    source_uuid,
    cost_category_id,
    raw_currency,
    distributed_cost
)
    SELECT uuid_generate_v4() as id,
        cluster_id,
        cluster_alias,
        array_agg(DISTINCT resource_id) as resource_ids,
        count(DISTINCT resource_id) as resource_count,
        max(data_source) as data_source,
        usage_start as usage_start,
        usage_start as usage_end,
        sum(infrastructure_raw_cost) as infrastructure_raw_cost,
        sum(infrastructure_markup_cost) as infrastructure_markup_cost,
        0 as infrastructure_data_in_gigabytes,
        sum(infrastructure_data_out_gigabytes),
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        cost_model_rate_type,
        {{source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id,
        max(raw_currency) as raw_currency,
        sum(distributed_cost) as distributed_cost
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND data_source = 'Pod'
        AND namespace = 'Network unattributed'
        AND infrastructure_data_out_gigabytes IS NOT NULL
    GROUP BY usage_start, cluster_id, cluster_alias, cost_model_rate_type
;
