INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
    monthly_cost_type,
    cost_category_id
)
WITH
    max_interval_data AS (
        SELECT
            max(interval_start) AS max_interval_start,
            vm_name
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
        WHERE
            source = {{source_uuid | string}}
            AND year = {{year}}
            AND month = {{month}}
        GROUP BY
            vm_name
    ),
    node_info AS (
        SELECT
            latest.node AS name_of_node,
            latest.resource_id AS resource_id,
            latest.vm_name AS name_of_vm
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items AS latest
        INNER JOIN max_interval_data AS max
            ON max.max_interval_start = latest.interval_start
            AND max.vm_name = latest.vm_name
        WHERE
            latest.source = {{source_uuid | string}}
            AND latest.year = {{year}}
            AND latest.month = {{month}}
    ),
    vm_resource_summary AS (
        SELECT
            vm_map.vm_cpu_request_cores AS vm_cpu_cores,
            max(DATE(vm_map.interval_start)) AS interval_day,
            vm_map.vm_name AS vm_name,
            max(node.name_of_node) AS node_name,
            max(node.resource_id) AS resource_id
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items_daily AS vm_map
        INNER JOIN node_info AS node
            ON node.name_of_vm = vm_map.vm_name
        WHERE
            vm_map.source = {{source_uuid | string}}
            AND vm_map.year = {{year}}
            AND vm_map.month = {{month}}
        GROUP BY
            1, vm_map.vm_name
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
    max(vmhrs.node_name) AS node,
    max(vmhrs.resource_id) AS resource_id,
    lids.pod_labels,
    lids.all_labels,
    lids.source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    max(vmhrs.vm_cpu_cores) * CAST({{ default_rate }} AS DECIMAL(33, 15)) / {{amortized_denominator}} AS cost_model_cpu_cost,
    {{cost_type}} AS monthly_cost_type,
    lids.cost_category_id
FROM
    postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
INNER JOIN
    vm_resource_summary AS vmhrs
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vmhrs.vm_name
WHERE
    lids.usage_start >= DATE({{start_date}})
    AND lids.usage_start <= DATE({{end_date}})
    AND lids.report_period_id = {{report_period_id}}
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
    lids.pod_labels,
    lids.all_labels
HAVING max(vmhrs.vm_cpu_cores) * CAST({{ default_rate }} AS DECIMAL(33, 15)) / {{amortized_denominator}} > 0;
