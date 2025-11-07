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
SELECT uuid_generate_v4(),
    {{report_period_id}},
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'GPU' as data_source,
    gpu.usage_start,
    gpu.usage_end,
    gpu.namespace,
    gpu.node,
    gpu.gpu_uuid as resource_id,
    jsonb_build_object(
        'gpu-model', gpu.gpu_model_name,
        'gpu-vendor', gpu.gpu_vendor_name
    ) as pod_labels,
    jsonb_build_object(
        'gpu-model', gpu.gpu_model_name,
        'gpu-vendor', gpu.gpu_vendor_name
    ) as all_labels,
    gpu.source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    -- GPU cost calculation: (rate / amortized_denominator) * gpu_count * (uptime in days)
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal) / CAST({{amortized_denominator}} as decimal)) * gpu.gpu_count * (gpu.gpu_pod_uptime / 86400.0),
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN gpu.gpu_model_name = {{ value }}
        THEN (CAST({{ value_rate }} AS decimal) / CAST({{amortized_denominator}} as decimal)) * gpu.gpu_count * (gpu.gpu_pod_uptime / 86400.0)
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{ default_rate }} AS decimal) / CAST({{amortized_denominator}} as decimal)) * gpu.gpu_count * (gpu.gpu_pod_uptime / 86400.0)
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    CAST({{ default_rate }} AS decimal) / CAST({{amortized_denominator}} as decimal)) * gpu.gpu_count * (gpu.gpu_pod_uptime / 86400.0),
    {%- else %}
    CAST(0 as decimal),
    {%- endif %}
    0 as cost_model_memory_cost,
    0 as cost_model_volume_cost,
    'Tag' as monthly_cost_type,
    gpu.cost_category_id
FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily AS gpu
WHERE gpu.usage_start >= DATE({{start_date}})
  AND gpu.usage_start <= DATE({{end_date}})
  AND gpu.report_period_id = {{report_period_id}}
  AND gpu.gpu_model_name IS NOT NULL
  AND gpu.month = {{month}}
  AND gpu.year = {{year}}
  {%- if value_rates is defined %}
  AND (
      {%- for value, value_rate in value_rates.items() %}
      {%- if not loop.first %} OR {%- endif %} gpu.gpu_model_name = {{value}}
      {%- endfor %}
  )
  {%- endif %}
;
