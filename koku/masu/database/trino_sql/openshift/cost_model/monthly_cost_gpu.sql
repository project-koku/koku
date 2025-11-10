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
    monthly_cost_type,
    cost_category_id
)
SELECT
    cast(uuid() as varchar) as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'GPU' as data_source,
    date(gpu.interval_start) as usage_start,
    date(gpu.interval_start) as usage_end,
    gpu.namespace,
    gpu.node,
    gpu.gpu_uuid as resource_id,
    json_format(cast(map(
        ARRAY['gpu-model', 'gpu-vendor', 'gpu-memory-mib', 'pod-name'],
        ARRAY[
            gpu.gpu_model_name,
            gpu.gpu_vendor_name,
            CAST(gpu.gpu_memory_capacity_mib AS varchar),
            gpu.pod
        ]
    ) as json)) as pod_labels,
    json_format(cast(map(
        ARRAY['gpu-model', 'gpu-vendor', 'gpu-memory-mib', 'pod-name'],
        ARRAY[
            gpu.gpu_model_name,
            gpu.gpu_vendor_name,
            CAST(gpu.gpu_memory_capacity_mib AS varchar),
            gpu.pod
        ]
    ) as json)) as all_labels,
    CAST(gpu.source AS varchar) as source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    -- GPU cost calculation: (rate / days_in_month) * (uptime_seconds / 86400)
    -- Formula: daily_rate * uptime_as_fraction_of_day
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0),
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        {%- if value.startswith('{') %}
        {%- set rate_spec = value | from_json %}
        -- JSON format: {"model": "A100", "vendor": "NVIDIA"}
        WHEN gpu.gpu_model_name = '{{rate_spec.model}}' AND gpu.gpu_vendor_name = '{{rate_spec.vendor}}'
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0)
        {%- else %}
        -- Simple format: just model name (backward compatible)
        WHEN gpu.gpu_model_name = {{value}}
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0)
        {%- endif %}
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0)
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0),
    {%- else %}
    CAST(0 AS decimal(24,9)),
    {%- endif %}
    CAST(0 AS decimal(24,9)) as cost_model_memory_cost,
    CAST(0 AS decimal(24,9)) as cost_model_volume_cost,
    'Tag' as monthly_cost_type,
    cat_ns.cost_category_id
FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
    ON gpu.namespace LIKE cat_ns.namespace
WHERE date(gpu.interval_start) >= DATE({{start_date}})
  AND date(gpu.interval_start) <= DATE({{end_date}})
  AND gpu.source = {{source}}
  AND gpu.year = {{year}}
  AND gpu.month = {{month}}
  AND gpu.gpu_model_name IS NOT NULL
  AND gpu.gpu_vendor_name IS NOT NULL
  {%- if value_rates is defined %}
  AND (
      {%- for value, value_rate in value_rates.items() %}
      {%- if not loop.first %} OR {%- endif %}
      {%- if value.startswith('{') %}
      {%- set rate_spec = value | from_json %}
      (gpu.gpu_model_name = '{{rate_spec.model}}' AND gpu.gpu_vendor_name = '{{rate_spec.vendor}}')
      {%- else %}
      gpu.gpu_model_name = {{value}}
      {%- endif %}
      {%- endfor %}
  )
  {%- endif %}
;
