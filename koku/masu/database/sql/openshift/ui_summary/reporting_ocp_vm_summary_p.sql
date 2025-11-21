DELETE FROM {{schema | sqlsafe}}.reporting_ocp_vm_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

WITH cte_latest_pod_labels AS (
    -- Selects pod labels from the second-to-last day with valid VM data.
    -- If only one day matches, that day is used instead.
    -- Prevents failures in test environments with limited data.
    SELECT DISTINCT ON (vm_name)
        all_labels->>'vm_kubevirt_io_name' AS vm_name,
        pod_labels as pod_labels
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start::date = (
        SELECT day FROM (
            SELECT DISTINCT usage_start::date AS day
            FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= {{start_date}}::date
                AND usage_start <= {{end_date}}::date
                AND source_uuid = {{source_uuid}}
                AND pod_request_cpu_core_hours IS NOT NULL
            ORDER BY day DESC
            LIMIT 2
        ) latest_days
        ORDER BY day
        LIMIT 1
    )
    AND pod_request_cpu_core_hours IS NOT NULL
    AND all_labels ? 'vm_kubevirt_io_name'
    ORDER BY vm_name, usage_start DESC
),
cte_latest_resources as (
    SELECT
        latest.vm_name as vm_name,
        max(latest.cpu_request) as cpu_request_hours,
        max(latest.mem_request) as memory_request_hours,
        max(latest.node) as node_name,
        labels.pod_labels as labels
    FROM cte_latest_pod_labels as labels
    INNER JOIN {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} as latest
    ON labels.vm_name = latest.vm_name
    GROUP BY latest.vm_name, labels.pod_labels
)
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
    cost_model_gpu_cost,
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
    max(latest.node_name) as node,
    latest.labels->>'vm_kubevirt_io_name' as vm_name,
        sum(cost_model_cpu_cost) as cost_model_cpu_cost,
        sum(cost_model_memory_cost) as cost_model_memory_cost,
        cost_model_rate_type,
        sum(cost_model_volume_cost) as cost_model_volume_cost,
        sum(cost_model_gpu_cost) as cost_model_gpu_cost,
        sum(distributed_cost) as distributed_cost,
    latest.labels as pod_labels,
    max(latest.cpu_request_hours) as pod_request_cpu_core_hours,
    max(latest.memory_request_hours) as pod_request_memory_gigabyte_hours,
    sum(infrastructure_markup_cost) as infrastructure_markup_cost,
    sum(infrastructure_raw_cost) as infrastructure_raw_cost,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(usage_start) as usage_start,
    max(usage_start) as usage_end,
    max(cost_category_id) as cost_category_id,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
INNER JOIN cte_latest_resources as latest
    ON latest.vm_name = ocp.pod_labels->>'vm_kubevirt_io_name'
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
GROUP BY cluster_alias, cluster_id, namespace, latest.node_name, vm_name, cost_model_rate_type, latest.labels
;


-- Platform Distribution
WITH cte_distribution_type AS (
    -- get the distribution type from the cost model associated with this source
    SELECT
        {{source_uuid}}::uuid as source_uuid,
        coalesce(max(cm.distribution), 'cpu')  as dt -- coalesce(max()) to return 'cpu' if a cost model does not exist for source
    FROM {{schema | sqlsafe}}.cost_model_map as cmm
    JOIN {{schema | sqlsafe}}.cost_model as cm
        ON cmm.cost_model_id = cm.uuid
    WHERE cmm.provider_uuid = {{source_uuid}}
),
cte_node_usage AS (
    SELECT
        namespace,
        node,
        usage_start,
        sum(pod_effective_usage_cpu_core_hours) as cpu_usage,
        sum(pod_effective_usage_memory_gigabyte_hours) as mem_usage
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY namespace, node, usage_start
),
cte_latest_resources AS (
    SELECT
        pod_labels->>'vm_kubevirt_io_name' AS vm_name,
        CASE WHEN cte_distribution_type.dt = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / sum(cte_node_usage.cpu_usage)
            ELSE sum(pod_effective_usage_memory_gigabyte_hours) / sum(cte_node_usage.mem_usage)
        END as ratio,
        cte_node_usage.node as node_name,
        cte_node_usage.namespace as namespace_name,
        pod_labels as labels,
        cte_node_usage.usage_start
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN cte_distribution_type
        ON cte_distribution_type.source_uuid = ocp.source_uuid
    JOIN cte_node_usage
        ON cte_node_usage.namespace = ocp.namespace
        AND cte_node_usage.node = ocp.node
        AND cte_node_usage.usage_start = ocp.usage_start
    WHERE pod_labels ? 'vm_kubevirt_io_name'
        AND pod_effective_usage_cpu_core_hours != 0
        AND pod_effective_usage_memory_gigabyte_hours != 0
    GROUP BY vm_name, cte_distribution_type.dt, cte_node_usage.usage_start, cte_node_usage.node, cte_node_usage.namespace, pod_labels
)
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_vm_summary_p (
    id,
    cluster_alias,
    cluster_id,
    namespace,
    node,
    vm_name,
    cost_model_rate_type,
    distributed_cost,
    pod_labels,
    raw_currency,
    resource_ids,
    usage_start,
    usage_end,
    source_uuid
)
SELECT
    uuid_generate_v4() as id,
    cluster_alias,
    cluster_id,
    namespace,
    node,
    latest.vm_name as vm_name,
    cost_model_rate_type,
    sum(distributed_cost * latest.ratio) as distributed_cost, -- the only cost inserted in this statement
    pod_labels,
    max(raw_currency) as raw_currency,
    array_agg(DISTINCT resource_id) as resource_ids,
    min(latest.usage_start) as usage_start,
    max(latest.usage_start) as usage_end,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN cte_latest_resources as latest
    ON latest.node_name = ocp.node
    AND latest.namespace_name = ocp.namespace
    AND latest.usage_start = ocp.usage_start
WHERE source_uuid = {{source_uuid}}
    AND distributed_cost != 0
GROUP BY cluster_alias, cluster_id, namespace, node, vm_name, pod_labels, cost_model_rate_type

;

-- Storage
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
    cost_model_gpu_cost,
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
    -- Selects the second-to-last day.
    -- If only one day matches, that day is returned instead.
    -- This prevents the query from breaking when the dataset is small (tests).
    SELECT day FROM (
        SELECT DISTINCT usage_start::date AS day
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
        WHERE usage_start >= {{start_date}}::date
            AND usage_start <= {{end_date}}::date
            AND source_uuid = {{source_uuid}}
            AND persistentvolumeclaim IS NOT NULL
        ORDER BY day DESC
        LIMIT 2
    ) latest_days
    ORDER BY day
    LIMIT 1
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
        AND ocp.persistentvolumeclaim IS NOT NULL
        AND map.pvc_name IS NOT NULL
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
        sum(cost_model_gpu_cost) as cost_model_gpu_cost,
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
    AND ocp.node IS NOT NULL
    AND ocp.resource_id IS NOT NULL
    AND ocp.persistentvolumeclaim IS NOT NULL
    AND namespace IS DISTINCT FROM 'Worker unallocated'
    AND namespace IS DISTINCT FROM 'Platform unallocated'
    AND namespace IS DISTINCT FROM 'Network unattributed'
    AND namespace IS DISTINCT FROM 'Storage unattributed'
GROUP BY storage.combined_labels, cluster_alias, cluster_id, namespace, vm_name, cost_model_rate_type, ocp.persistentvolumeclaim;

TRUNCATE TABLE {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}};
DROP TABLE {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}};
