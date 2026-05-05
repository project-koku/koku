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
WITH
    vm_max_interval AS (
        SELECT
            vm_name,
            max(interval_start) AS max_interval_start
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items
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
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items AS node_info
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
            vm_map.usage_start AS interval_day,
            vm_map.vm_name AS vm_name
        FROM {{schema | sqlsafe}}.openshift_vm_usage_line_items_daily AS vm_map
        WHERE
            vm_map.source = {{source_uuid | string}}
            AND vm_map.year = {{year}}
            AND vm_map.month = {{month}}
        GROUP BY
            1, 2, vm_map.vm_name
    )
SELECT
    uuid_generate_v4(),
    {{cost_model_id}} AS cost_model_id,
    {{report_period_id}} AS report_period_id,
    lids.source_uuid,
    lids.usage_start,
    lids.usage_end,
    max(latest.node_name) AS node,
    lids.namespace,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    NULL AS persistentvolumeclaim,
    lids.pod_labels,
    NULL::jsonb AS volume_labels,
    lids.all_labels,
    encode(sha256(decode(COALESCE(lids.pod_labels::text, '') || '|' || COALESCE((NULL::jsonb)::text, '') || '|' || COALESCE(lids.all_labels::text, ''), 'escape')), 'hex') AS label_hash,
    {{custom_name}} AS custom_name,
    {{metric_type}} AS metric_type,
    {{rate_type}} AS cost_model_rate_type,
    'Tag' AS monthly_cost_type,
    {%- if value_rates is defined and value_rates %}
    CASE
        {%- for value, rate in value_rates.items() %}
        WHEN lids.pod_labels->>'{{ tag_key|sqlsafe }}' = {{value}}
        THEN (max(vm_usage.vm_cpu_cores) * CAST({{rate}} AS DECIMAL(33, 15))) / {{amortized_denominator}}
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (max(vm_usage.vm_cpu_cores) * CAST({{default_rate}} AS DECIMAL(33, 15))) / {{amortized_denominator}}
        {%- endif %}
    END AS calculated_cost,
    {%- else %}
    (max(vm_usage.vm_cpu_cores) * CAST({{default_rate}} AS DECIMAL(33, 15))) / {{amortized_denominator}} AS calculated_cost,
    {%- endif %}
    lids.cost_category_id,
    {{rate_uuid}} AS rate_id
FROM
    {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN
    vm_usage_summary AS vm_usage
    ON lids.pod_labels->>'vm_kubevirt_io_name' = vm_usage.vm_name
    AND lids.usage_start = vm_usage.interval_day
LEFT JOIN
    latest_vm_node_info AS latest
    ON lids.pod_labels->>'vm_kubevirt_io_name' = latest.name_of_vm
WHERE
    lids.usage_start >= DATE({{start_date}})
    AND lids.usage_start <= DATE({{end_date}})
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.pod_usage_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours IS NOT NULL
    AND lids.monthly_cost_type IS NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
{%- if default_rate is defined %}
    AND lids.pod_labels->>'{{ tag_key|sqlsafe }}' IS NOT NULL
{%- else %}
    AND (
        {%- for value, rate in value_rates.items() %}
            {%- if not loop.first %} OR {%- endif %} lids.pod_labels->>'{{ tag_key|sqlsafe }}' = {{value}}
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
RETURNING 1;
