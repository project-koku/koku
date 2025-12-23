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
    monthly_cost_type,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_category_id
)
SELECT uuid_generate_v4(),
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
    'Tag' AS monthly_cost_type,
    {{rate_type}} AS cost_model_rate_type,
    {%- if value_rates is defined and value_rates %}
    CASE
        {%- for value, rate in value_rates.items() %}
        WHEN lids.pod_labels::json->>'{{ tag_key|sqlsafe }}' = {{value}}
        THEN max(vmhrs.vm_interval_hours) * CAST({{rate}} as DECIMAL(33, 15))
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE max(vmhrs.vm_interval_hours) * CAST({{default_rate}} as DECIMAL(33, 15))
        {%- endif %}
    END as cost_model_cpu_cost,
    {%- else %}
    max(vmhrs.vm_interval_hours) * CAST({{default_rate}} as DECIMAL(33, 15)) AS cost_model_cpu_cost,
    {%- endif %}
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN (
    {%- if use_fractional_hours %}
    SELECT
        vm_name,
        DATE(interval_start) AS interval_day,
        sum(vm_uptime_total_seconds) / 3600 AS vm_interval_hours
    FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items
    WHERE source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
    {%- else %}
    SELECT
        pod_labels::json->>'vm_kubevirt_io_name' AS vm_name,
        DATE(interval_start) AS interval_day,
        count(interval_start) AS vm_interval_hours
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE strpos(pod_labels, 'vm_kubevirt_io_name') != 0
      AND source = {{source_uuid}}
      AND year = {{year}}
      AND month = {{month}}
    GROUP BY 1, 2
    {%- endif %}
) AS vmhrs
ON lids.pod_labels::json->>'vm_kubevirt_io_name' = vmhrs.vm_name
   AND DATE(vmhrs.interval_day) = lids.usage_start
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
{%- if default_rate is defined %}
    AND lids.pod_labels::json->'{{ tag_key|sqlsafe }}' IS NOT NULL
{%- else %}
        AND (
            {%- for value, rate in value_rates.items() %}
                {%- if not loop.first %} OR {%- endif %} lids.pod_labels::json->>'{{ tag_key|sqlsafe }}' = {{value}}
                {%- if loop.last %} ) {%- endif %}
            {%- endfor %}
{%- endif %}
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
