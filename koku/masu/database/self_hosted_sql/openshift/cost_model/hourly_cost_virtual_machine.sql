-- Phase 3: RTU INSERT
INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
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
SELECT uuid_generate_v4(),
    {{cost_model_id}} AS cost_model_id,
    {{report_period_id}} AS report_period_id,
    source_uuid,
    usage_start,
    usage_end,
    node,
    namespace,
    cluster_id,
    cluster_alias,
    data_source,
    NULL AS persistentvolumeclaim,
    pod_labels,
    NULL::jsonb AS volume_labels,
    all_labels,
    md5(COALESCE(pod_labels::text, '') || '|' || COALESCE((NULL::jsonb)::text, '') || '|' || COALESCE(all_labels::text, '')) AS label_hash,
    {{custom_name}} AS custom_name,
    'cpu' AS metric_type,
    {{rate_type}} AS cost_model_rate_type,
    NULL AS monthly_cost_type,
    max(vmhrs.vm_interval_hours) * CAST({{hourly_rate}} as DECIMAL(33, 15)) AS calculated_cost,
    cost_category_id,
    {{rate_uuid}} AS rate_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
{%- if use_fractional_hours %}
JOIN (
    SELECT
        vm_name,
        usage_start as interval_day,
        sum(vm_uptime_total_seconds) / 3600 AS vm_interval_hours
    FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
) AS vmhrs
    ON lids.pod_labels->>'vm_kubevirt_io_name' = vmhrs.vm_name
    AND vmhrs.interval_day = lids.usage_start
{%- else %}
JOIN (
    SELECT
        pod_labels::jsonb->>'vm_kubevirt_io_name' as vm_name,
        usage_start as interval_day,
        count(interval_start) AS vm_interval_hours
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE strpos(pod_labels, 'vm_kubevirt_io_name') != 0
      AND source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
) AS vmhrs
    ON lids.pod_labels->>'vm_kubevirt_io_name' = vmhrs.vm_name
    AND vmhrs.interval_day = lids.usage_start
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
RETURNING 1;
