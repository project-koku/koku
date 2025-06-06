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
    cost_category_id
)
SELECT uuid(),
    {{report_period_id}} AS report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    max(vmhrs.node_name) as node,
    max(vmhrs.resource_id) AS resource_id,
    pod_labels,
    all_labels,
    source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    max(vmhrs.vm_interval_hours) * max(vmhrs.vm_cpu_cores) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
INNER JOIN (
    SELECT
        vm_cpu_request_cores as vm_cpu_cores,
        DATE(interval_start) as interval_day,
        vm_map.vm_name as vm_name,
        count(interval_start) as vm_interval_hours,
        max(node.name_of_node) as node_name,
        max(node.resource_id) as resource_id
    FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items as vm_map
        INNER JOIN (
            SELECT
                node as name_of_node,
                resource_id as resource_id,
                latest.vm_name as name_of_vm
            FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items as latest
            INNER JOIN (
                    SELECT max(interval_start) as max_interval_start, vm_name
                    FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
                    WHERE source = {{source_uuid | string}}
                        AND year = {{year}}
                        AND month = {{month}}
                    GROUP BY vm_name
                ) as max
            ON max.max_interval_start = latest.interval_start
            AND max.vm_name = latest.vm_name
            WHERE source = {{source_uuid | string}}
                AND year = {{year}}
                AND month = {{month}}
        ) AS node
        ON node.name_of_vm = vm_map.vm_name
        WHERE source = {{source_uuid | string}}
            AND year = {{year}}
            AND month = {{month}}
    group by 1, 2, vm_map.vm_name
) AS vmhrs
ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vmhrs.vm_name
    AND DATE(vmhrs.interval_day) = lids.usage_start
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND pod_usage_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours IS NOT NULL
    AND monthly_cost_type IS NULL
GROUP BY usage_start,
    usage_end,
    source_uuid,
    cluster_id,
    cluster_alias,
    namespace,
    data_source,
    cost_category_id,
    pod_labels,
    all_labels
;
