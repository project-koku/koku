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
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_category_id
)

-- get vms from daily table
WITH cte_vms AS (
SELECT
    DISTINCT json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') AS vm_name
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
WHERE json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') IS NOT NULL
    AND usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND source_uuid = CAST({{source_uuid}} as uuid)
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
),

-- get number of hours for every time we see a vm label
cte_vm_usage_hours AS (
    SELECT
        cte_vms.vm_name,
        DATE(interval_start) as interval_day,
        count(pod_usage.interval_start) AS vm_interval_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items pod_usage
    INNER JOIN cte_vms
        ON json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name') = cte_vms.vm_name
    WHERE strpos(lower(pod_labels), 'vm_kubevirt_io_name": "') != 0
        AND source = {{source_uuid}}
        AND year={{year}}
        AND month={{month}}
    GROUP BY vm_name, DATE(interval_start)
)

SELECT uuid(),
    max(report_period_id) AS report_period_id,
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
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_vm_usage_hours AS vmhrs
    ON json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') = vmhrs.vm_name
    AND vmhrs.interval_day=lids.usage_start
    AND vmhrs.interval_day=lids.usage_end
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND json_extract_scalar(all_labels, '$.vm_kubevirt_io_name') IS NOT NULL
    AND pod_usage_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
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
