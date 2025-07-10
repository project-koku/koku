WITH
    vm_max_interval AS (
        SELECT
            vm_name,
            max(interval_start) AS max_interval_start
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
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
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items AS node_info
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
            {% if use_fractional_hours %}
                sum(vm_map.vm_uptime_total_seconds) AS vm_interval_hours
            {% else %}
                count(vm_map.interval_start) AS vm_interval_hours
            {% endif %}
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items AS vm_map
        WHERE
            vm_map.source = {{source_uuid | string}}
            AND vm_map.year = {{year}}
            AND vm_map.month = {{month}}
        GROUP BY
            1, 2, vm_map.vm_name
    ),
    latest_vm_labels AS (
        SELECT
            json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') AS vm_name,
            CAST(
                REDUCE(
                    ARRAY_AGG(
                        map_concat(
                            COALESCE(CAST(lids.pod_labels AS map(varchar, varchar)), MAP()),
                            COALESCE(CAST(lids.all_labels AS map(varchar, varchar)), MAP())
                        )
                    ),
                    MAP(),
                    (s, x) -> map_concat(s, x),
                    s -> s
                )
            AS JSON) AS combined_labels
        FROM
            postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
        JOIN vm_max_interval as max
            ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = max.vm_name
            AND DATE(lids.usage_start) = DATE(max.max_interval_start)
        WHERE lids.report_period_id = {{report_period_id}}
            AND lids.data_source = 'Pod'
            AND lids.pod_usage_cpu_core_hours IS NOT NULL
            AND lids.pod_request_cpu_core_hours IS NOT NULL
            AND lids.monthly_cost_type IS NULL
        GROUP BY json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name')
    )
SELECT
    uuid(),
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
    {% if use_fractional_hours %}
        max(vm_usage.vm_interval_hours) / 3600 * max(vm_usage.vm_cpu_cores) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    {% else %}
        max(vm_usage.vm_interval_hours) * max(vm_usage.vm_cpu_cores) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    {% endif %}
    lids.cost_category_id
FROM
    postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN
    vm_usage_summary AS vm_usage
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vm_usage.vm_name
    AND lids.usage_start = vm_usage.interval_day
JOIN
    latest_vm_node_info AS latest
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = latest.name_of_vm
JOIN latest_vm_labels as labels
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = labels.vm_name
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.pod_usage_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours IS NOT NULL
    AND lids.monthly_cost_type IS NULL
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
