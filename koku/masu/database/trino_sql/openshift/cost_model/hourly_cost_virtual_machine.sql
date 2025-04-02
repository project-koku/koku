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
    node,
    max(resource_id) AS resource_id,
    pod_labels,
    all_labels,
    source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    max(vmhrs.vm_interval_hours) * CAST({{vm_cost_per_hour}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN (
    SELECT
        json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name') as vm_name,
        DATE(pod_usage.interval_start) as interval_day,
        count(pod_usage.interval_start) AS vm_interval_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items pod_usage
    WHERE strpos(pod_usage.pod_labels, 'vm_kubevirt_io_name') != 0
        AND source = {{source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
    GROUP BY 1, 2
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
    node,
    namespace,
    data_source,
    cost_category_id,
    pod_labels,
    all_labels
;
