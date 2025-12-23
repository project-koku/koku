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
    resource_id,
    pod_labels,
    all_labels,
    source_uuid,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_category_id
)
WITH
    vm_max_interval AS (
        SELECT
            vm_name,
            max(interval_start) AS max_interval_start
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items
        WHERE
            source = {{source_uuid | string}}
            AND year = {{year}}
            AND month = {{month}}
        GROUP BY
            vm_name
    ),
    latest_vm_node_info AS (
        SELECT
           node_info.vm_name as name_of_vm,
           node_info.node AS node_name,
           node_info.resource_id AS resource_id
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items AS node_info
        INNER JOIN vm_max_interval AS vmi
            ON node_info.vm_name = vmi.vm_name
            AND node_info.interval_start = vmi.max_interval_start
        WHERE
           node_info.source = {{source_uuid | string}}
            AND node_info.year = {{year}}
            AND node_info.month = {{month}}
    ),
    vm_usage_summary AS (
        SELECT
            vm_map.vm_cpu_request_cores AS vm_cpu_cores,
            DATE(vm_map.interval_start) AS interval_day,
            vm_map.vm_name AS vm_name,
            sum(vm_map.vm_uptime_total_seconds) AS vm_interval_hours
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items AS vm_map
        WHERE
            vm_map.source = {{source_uuid | string}}
            AND vm_map.year = {{year}}
            AND vm_map.month = {{month}}
        GROUP BY
            1, 2, vm_map.vm_name
    ),
    latest_vm_labels AS (
        SELECT
            lids.pod_labels::json->>'vm_kubevirt_io_name' AS vm_name,
            (
                SELECT jsonb_object_agg(key, value)::text
                FROM (
                    SELECT DISTINCT ON (key) key, value
                    FROM (
                        SELECT t.key, t.value
                        FROM unnest(array_agg(COALESCE(lids.pod_labels::jsonb, '{}'::jsonb) || COALESCE(lids.all_labels::jsonb, '{}'::jsonb))) AS obj,
                        LATERAL jsonb_each_text(obj) AS t(key, value)
                    ) all_pairs
                    ORDER BY key, value DESC
                ) unique_pairs
            ) AS combined_labels
        FROM
            {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
        JOIN vm_max_interval as max
            ON lids.pod_labels::json->>'vm_kubevirt_io_name' = max.vm_name
            AND DATE(lids.usage_start) = DATE(max.max_interval_start)
        WHERE lids.report_period_id = {{report_period_id}}
            AND lids.data_source = 'Pod'
            AND lids.pod_usage_cpu_core_hours IS NOT NULL
            AND lids.pod_request_cpu_core_hours IS NOT NULL
            AND lids.monthly_cost_type IS NULL
        GROUP BY lids.pod_labels::json->>'vm_kubevirt_io_name'
    )
SELECT
    uuid_generate_v4(),
    {{report_period_id}} AS report_period_id,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    lids.usage_start,
    lids.usage_end,
    lids.namespace,
    max(latest.node_name) AS node,
    max(latest.resource_id) AS resource_id,
    labels.combined_labels as pod_labels,
    labels.combined_labels as all_labels,
    lids.source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    max(vm_usage.vm_interval_hours) / 3600 * max(vm_usage.vm_cpu_cores) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    lids.cost_category_id
FROM
    {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN
    vm_usage_summary AS vm_usage
    ON lids.pod_labels::json->>'vm_kubevirt_io_name' = vm_usage.vm_name
    AND lids.usage_start = vm_usage.interval_day
JOIN
    latest_vm_node_info AS latest
    ON lids.pod_labels::json->>'vm_kubevirt_io_name' = latest.name_of_vm
JOIN latest_vm_labels as labels
    ON lids.pod_labels::json->>'vm_kubevirt_io_name' = labels.vm_name
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.pod_usage_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours IS NOT NULL
    AND lids.monthly_cost_type IS NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
GROUP BY
    lids.usage_start,
    lids.usage_end,
    lids.source_uuid,
    lids.cluster_id,
    lids.cluster_alias,
    lids.namespace,
    lids.data_source,
    lids.cost_category_id,
    labels.combined_labels
;
