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
    pod_labels,
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
WITH
    vm_max_interval AS (
        SELECT
            vm_name,
            max(interval_start) AS max_interval_start
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
        WHERE
            source = {{source_uuid}}
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
           node_info.source = {{source_uuid}}
            AND node_info.year = {{year}}
            AND node_info.month = {{month}}
    ),
    vm_usage_summary AS (
        SELECT
            vm_map.vm_cpu_request_cores AS vm_cpu_cores,
            DATE(vm_map.interval_start) AS interval_day,
            vm_map.vm_name AS vm_name,
            sum(vm_map.vm_uptime_total_seconds) / 3600 AS vm_interval_hours
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items AS vm_map
        WHERE
            vm_map.source = {{source_uuid | string}}
            AND vm_map.year = {{year}}
            AND vm_map.month = {{month}}
        GROUP BY
            1, 2, vm_map.vm_name
    )
SELECT
    uuid(),
    CAST({{cost_model_id}} AS uuid) AS cost_model_id,
    {{report_period_id}} AS report_period_id,
    lids.source_uuid,
    lids.usage_start,
    lids.usage_end,
    max(latest.node_name) AS node,
    lids.namespace,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    lids.pod_labels,
    lids.all_labels,
    max(to_hex(sha256(to_utf8(COALESCE(json_format(CAST(lids.pod_labels AS json)), '') || '|' || '' || '|' || COALESCE(json_format(CAST(lids.all_labels AS json)), ''))))) AS label_hash,
    {{custom_name}} AS custom_name,
    {{metric_type}} AS metric_type,
    {{rate_type}} AS cost_model_rate_type,
    'Tag' AS monthly_cost_type,
    {%- if value_rates is defined and value_rates %}
    CASE
        {%- for value, rate in value_rates.items() %}
        WHEN json_extract_scalar(lids.pod_labels, '$.{{ tag_key|sqlsafe }}') = {{value}}
        THEN max(vm_usage.vm_cpu_cores) * CAST({{rate}} AS DECIMAL(33, 15)) * max(vm_usage.vm_interval_hours)
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE max(vm_usage.vm_cpu_cores) * CAST({{default_rate}} AS DECIMAL(33, 15)) * max(vm_usage.vm_interval_hours)
        {%- endif %}
    END AS calculated_cost,
    {%- else %}
    max(vm_usage.vm_cpu_cores) * CAST({{default_rate}} AS DECIMAL(33, 15)) * max(vm_usage.vm_interval_hours) AS calculated_cost,
    {%- endif %}
    lids.cost_category_id,
    CAST({{rate_uuid}} AS uuid) AS rate_id
FROM
    postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN
    vm_usage_summary AS vm_usage
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = vm_usage.vm_name
    AND lids.usage_start = vm_usage.interval_day
LEFT JOIN
    latest_vm_node_info AS latest
    ON json_extract_scalar(lids.pod_labels, '$.vm_kubevirt_io_name') = latest.name_of_vm
WHERE
    lids.usage_start >= DATE({{start_date}})
    AND lids.usage_start <= DATE({{end_date}})
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.pod_usage_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours IS NOT NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
{%- if default_rate is defined %}
    AND json_extract(lids.pod_labels, '$.{{ tag_key|sqlsafe }}') IS NOT NULL
{%- else %}
    AND (
        {%- for value, rate in value_rates.items() %}
            {%- if not loop.first %} OR {%- endif %} json_extract_scalar(lids.pod_labels, '$.{{ tag_key|sqlsafe }}') = {{value}}
        {%- if loop.last %} ) {%- endif %}
        {%- endfor %}
{%- endif %}
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
;
