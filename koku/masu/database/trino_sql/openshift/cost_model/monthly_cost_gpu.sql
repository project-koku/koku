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
    all_labels,
    source_uuid,
    cost_model_rate_type,
    cost_model_gpu_cost,
    monthly_cost_type,
    cost_category_id
)
SELECT
    uuid() as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'GPU' as data_source,
    date(gpu.interval_start) as usage_start,
    date(gpu.interval_start) as usage_end,
    gpu.namespace as namespace,
    gpu.node as node,
    gpu.gpu_uuid as resource_id,
    cast(map(
        ARRAY['gpu-model', 'gpu-vendor', 'gpu-memory-mib', 'gpu-uptime-hours'],
        ARRAY[
            gpu.gpu_model_name,
            gpu.gpu_vendor_name,
            CAST(gpu.gpu_memory_capacity_mib AS varchar),
            CAST(gpu.gpu_pod_uptime / 3600.0 AS varchar)
        ]
    ) as json) as all_labels,
    CAST(gpu.source AS uuid) as source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    -- GPU cost calculation: (rate / days_in_month) * (uptime_seconds / 86400)
    -- Formula: daily_rate * uptime_as_fraction_of_day
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0),
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN gpu.gpu_model_name = '{{value | sqlsafe}}'
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0)
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0)
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0),
    {%- else %}
    0,
    {%- endif %}
    'Tag' AS monthly_cost_type,
    cat_ns.cost_category_id
FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
    ON gpu.namespace LIKE cat_ns.namespace
WHERE date(gpu.interval_start) >= DATE({{start_date}})
  AND date(gpu.interval_start) <= DATE({{end_date}})
  AND gpu.source = {{source_uuid}}
  AND gpu.year = {{year}}
  AND gpu.month = {{month}}
  AND gpu.gpu_vendor_name = '{{tag_key | sqlsafe}}'
  {%- if value_rates is defined %}
  AND (
      {%- for value, value_rate in value_rates.items() %}
      {%- if not loop.first %} OR {%- endif %}
      gpu.gpu_model_name = '{{value | sqlsafe}}'
      {%- endfor %}
  )
  {%- endif %}
;

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
    all_labels,
    source_uuid,
    cost_model_rate_type,
    cost_model_gpu_cost,
    monthly_cost_type
)
WITH cte_unutilized_uptime_hours AS (
    select
        node_ut.node,
        -- count(node_ut.interval_start) * max(CAST(json_extract_scalar(node_labels, '$.nvidia_com_gpu_count') as DECIMAL(33, 15))) as node_uptime_hours,
        -- max(gpu.aggregated_pod_uptime) as pod_uptime,
        count(node_ut.interval_start) * max(CAST(json_extract_scalar(node_labels, '$.nvidia_com_gpu_count') as DECIMAL(33, 15))) - coalesce(max(gpu.aggregated_pod_uptime), 0) as untilized_uptime,
        json_extract_scalar(node_ut.node_labels, '$.nvidia_com_gpu_product') as model,
        DATE(node_ut.interval_start) as interval_date
    from openshift_node_labels_line_items as node_ut
    LEFT JOIN (
        SELECT
            sum(gpu.gpu_pod_uptime) / 3600 as aggregated_pod_uptime,
            gpu.node,
            DATE(gpu.interval_start) as interval_date
        from openshift_gpu_usage_line_items_daily as gpu
            WHERE gpu.source = {{source_uuid}}
            AND gpu.year = {{year}}
            AND gpu.month = {{month}}
        group by node, DATE(gpu.interval_start)

    ) AS gpu
        ON gpu.node = node_ut.node
        AND gpu.interval_date = DATE(node_ut.interval_start)
    where node_labels like '%"nvidia_com_gpu_present": "True"%'
        AND node_ut.month = {{month}}
        AND node_ut.year = {{year}}
        AND node_ut.source = {{source_uuid}}
    group by node_ut.node, json_extract_scalar(node_labels, '$.nvidia_com_gpu_product'), DATE(node_ut.interval_start)
)
SELECT
    uuid() as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'GPU' as data_source,
    hrs.interval_date as usage_start,
    hrs.interval_date as usage_end,
    'GPU unallocated' as namespace,
    hrs.node,
    cast(map(
        ARRAY['gpu-model'],
        ARRAY[hrs.model]
    ) as json) as all_labels,
    CAST({{source_uuid}} AS uuid) as source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 AS decimal(24,9))) * hrs.untilized_uptime,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN hrs.model = '{{value | sqlsafe}}'
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 AS decimal(24,9))) * hrs.untilized_uptime
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 AS decimal(24,9))) * hrs.untilized_uptime
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 AS decimal(24,9))) * hrs.untilized_uptime,
    {%- else %}
    0,
    {%- endif %}
    'Tag' AS monthly_cost_type
FROM cte_unutilized_uptime_hours as hrs
WHERE untilized_uptime > 0
;
