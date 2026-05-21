-- Phase 3: RTU INSERT — VM hourly costs, flat rate
INSERT INTO postgres.{{schema | sqlsafe}}.rates_to_usage (
    uuid,
    cost_model_id,
    report_period_id,
    source_uuid,
    usage_start,
    usage_end,
    node,
    namespace,
    cluster_id,
    cluster_alias,
    data_source,
    persistentvolumeclaim,
    pod_labels,
    volume_labels,
    all_labels,
    label_hash,
    custom_name,
    metric_type,
    cost_model_rate_type,
    monthly_cost_type,
    calculated_cost,
    cost_category_id,
    rate_id
)
SELECT uuid(),
    CAST({{cost_model_id}} AS uuid) AS cost_model_id,
    {{report_period_id}} AS report_period_id,
    source_uuid,
    usage_start,
    usage_end,
    node,
    namespace,
    cluster_id,
    cluster_alias,
    data_source,
    CAST(NULL AS varchar) AS persistentvolumeclaim,
    pod_labels,
    CAST(NULL AS json) AS volume_labels,
    all_labels,
    max(to_hex(sha256(to_utf8(COALESCE(json_format(CAST(pod_labels AS json)), '') || '|' || '' || '|' || COALESCE(json_format(CAST(all_labels AS json)), ''))))) AS label_hash,
    {{custom_name}} AS custom_name,
    {{metric_type}} AS metric_type,
    {{rate_type}} AS cost_model_rate_type,
    CAST(NULL AS varchar) AS monthly_cost_type,
    max(vmhrs.vm_interval_hours) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS calculated_cost,
    cost_category_id,
    CAST({{rate_uuid}} AS uuid) AS rate_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
{%- if use_fractional_hours %}
JOIN (
    SELECT
        vm_name,
        DATE(interval_start) as interval_day,
        sum(vm_uptime_total_seconds) / 3600 AS vm_interval_hours
    FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
) AS vmhrs
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vmhrs.vm_name
    AND DATE(vmhrs.interval_day) = lids.usage_start
{%- else %}
JOIN (
    SELECT
        json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') as vm_name,
        DATE(interval_start) as interval_day,
        count(interval_start) AS vm_interval_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE strpos(pod_labels, 'vm_kubevirt_io_name') != 0
      AND source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
) AS vmhrs
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vmhrs.vm_name
    AND DATE(vmhrs.interval_day) = lids.usage_start
{%- endif %}
WHERE usage_start >= DATE({{start_date}})
    AND usage_start <= DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND pod_usage_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours IS NOT NULL
    AND monthly_cost_type IS NULL
    AND (
            lids.cost_model_rate_type IS NULL
            OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
        )
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
