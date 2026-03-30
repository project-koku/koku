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
        ARRAY['gpu-model', 'gpu-vendor', 'gpu-memory-mib', 'mig-profile', 'mig-slice-count', 'gpu-max-slices', 'mig-strategy', 'mig-memory-mib', 'gpu-mode'],
        ARRAY[
            gpu.gpu_model_name,
            gpu.gpu_vendor_name,
            CAST(gpu.gpu_memory_capacity_mib AS varchar),
            gpu.mig_profile,
            CAST(CAST(gpu.mig_slice_count AS INTEGER) AS varchar),
            CAST(CAST(gpu.gpu_max_slices AS INTEGER) AS varchar),
            gpu.mig_strategy,
            CAST(CAST(gpu.mig_memory_capacity_mib AS INTEGER) AS varchar),
            CASE WHEN gpu.mig_profile IS NOT NULL AND gpu.mig_profile != '' THEN 'MIG' ELSE 'dedicated' END
        ]
    ) as json) as all_labels,
    CAST(gpu.source AS uuid) as source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    -- GPU cost calculation with MIG slice support:
    -- For MIG: (rate / days_in_month) * (uptime_seconds / 86400) * (slice_count / max_slices)
    -- For dedicated: (rate / days_in_month) * (uptime_seconds / 86400)
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0) *
        CASE
            WHEN gpu.mig_slice_count IS NOT NULL AND gpu.gpu_max_slices IS NOT NULL AND gpu.gpu_max_slices > 0
            THEN CAST(gpu.mig_slice_count AS decimal(24,9)) / CAST(gpu.gpu_max_slices AS decimal(24,9))
            ELSE 1.0
        END,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN gpu.gpu_model_name = '{{value | sqlsafe}}'
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0) *
            CASE
                WHEN gpu.mig_slice_count IS NOT NULL AND gpu.gpu_max_slices IS NOT NULL AND gpu.gpu_max_slices > 0
                THEN CAST(gpu.mig_slice_count AS decimal(24,9)) / CAST(gpu.gpu_max_slices AS decimal(24,9))
                ELSE 1.0
            END
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0) *
            CASE
                WHEN gpu.mig_slice_count IS NOT NULL AND gpu.gpu_max_slices IS NOT NULL AND gpu.gpu_max_slices > 0
                THEN CAST(gpu.mig_slice_count AS decimal(24,9)) / CAST(gpu.gpu_max_slices AS decimal(24,9))
                ELSE 1.0
            END
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} AS decimal(24,9))) * (gpu.gpu_pod_uptime / 86400.0) *
        CASE
            WHEN gpu.mig_slice_count IS NOT NULL AND gpu.gpu_max_slices IS NOT NULL AND gpu.gpu_max_slices > 0
            THEN CAST(gpu.mig_slice_count AS decimal(24,9)) / CAST(gpu.gpu_max_slices AS decimal(24,9))
            ELSE 1.0
        END,
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
    -- MIG-aware unallocated GPU calculation per GPU model:
    -- total_gpu_slice_hours = node_uptime_hours * gpu_count * max_slices
    -- utilized_slice_hours = sum(pod_uptime * slice_count) / 3600
    -- unutilized_slice_hours = total_gpu_slice_hours - utilized_slice_hours
    --
    -- GPU count comes from node labels (nvidia_com_gpu_count) for accuracy.
    -- MIG strategy determines how unutilized capacity is calculated:
    --   mixed/NULL: capacity = uptime * gpu_count * max_slices (each GPU has max_slices slots)
    --   single: capacity = uptime * gpu_count (each GPU is one MIG slice)
    SELECT
        node_ut.node,
        regexp_replace(COALESCE(gpu.gpu_model_name, json_extract_scalar(node_ut.node_labels, '$.nvidia_com_gpu_product')), '[^a-zA-Z0-9]+', ' ') as model,
        DATE(node_ut.interval_start) as usage_start,
        gpu.max_slices_per_gpu as max_slices_per_gpu,
        CASE
            WHEN LOWER(TRIM(json_extract_scalar(node_ut.node_labels, '$.nvidia_com_mig_strategy'))) IS NULL OR LOWER(TRIM(json_extract_scalar(node_ut.node_labels, '$.nvidia_com_mig_strategy'))) = 'mixed'
                THEN count(node_ut.interval_start) * CAST(TRIM(json_extract_scalar(node_ut.node_labels, '$.nvidia_com_gpu_count')) AS DECIMAL(33, 15)) * gpu.max_slices_per_gpu - coalesce(max(gpu.aggregated_slice_uptime), 0)
            WHEN LOWER(TRIM(json_extract_scalar(node_ut.node_labels, '$.nvidia_com_mig_strategy'))) = 'single'
                THEN count(node_ut.interval_start) * CAST(TRIM(json_extract_scalar(node_ut.node_labels, '$.nvidia_com_gpu_count')) AS DECIMAL(33, 15)) - coalesce(max(gpu.aggregated_slice_uptime), 0)
            ELSE 0
        END as unutilized_uptime
    FROM openshift_node_labels_line_items as node_ut
    LEFT JOIN (
        SELECT
            sum(gpu.gpu_pod_uptime * COALESCE(gpu.mig_slice_count, 1)) / 3600 as aggregated_slice_uptime,
            max(COALESCE(gpu.gpu_max_slices, 1)) as max_slices_per_gpu,
            CAST(COUNT(DISTINCT gpu.gpu_uuid) AS DECIMAL(33, 15)) as physical_gpu_count,
            gpu.node,
            gpu.gpu_model_name,
            DATE(gpu.interval_start) as interval_date
        FROM hive.{{schema | sqlsafe}}.openshift_gpu_usage_line_items_daily as gpu
        WHERE gpu.source = {{source_uuid}}
            AND gpu.year = {{year}}
            AND gpu.month = {{month}}
            AND date(gpu.interval_start) >= DATE({{start_date}})
            AND date(gpu.interval_start) <= DATE({{end_date}})
            AND gpu.gpu_vendor_name = '{{tag_key | sqlsafe}}'
            {%- if value_rates is defined %}
            AND (
                {%- for value, value_rate in value_rates.items() %}
                {%- if not loop.first %} OR {%- endif %}
                gpu.gpu_model_name = '{{value | sqlsafe}}'
                {%- endfor %}
            )
            {%- endif %}
        GROUP BY gpu.node, gpu.gpu_model_name, DATE(gpu.interval_start)
    ) AS gpu
        ON gpu.node = node_ut.node
        AND gpu.interval_date = DATE(node_ut.interval_start)
    WHERE date(node_ut.interval_start) >= DATE({{start_date}})
        AND date(node_ut.interval_start) <= DATE({{end_date}})
        AND node_ut.month = {{month}}
        AND node_ut.year = {{year}}
        AND node_ut.source = {{source_uuid}}
        AND node_labels like '%"nvidia_com_gpu_present": "True"%'
    GROUP BY node_ut.node, gpu.gpu_model_name, DATE(node_ut.interval_start), gpu.max_slices_per_gpu,
             gpu.physical_gpu_count, gpu.aggregated_slice_uptime, node_ut.node_labels
)
SELECT
    uuid() as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'GPU' as data_source,
    hrs.usage_start as usage_start,
    hrs.usage_start as usage_end,
    'GPU unallocated' as namespace,
    hrs.node,
    cast(map(
        ARRAY['gpu-model', 'max-slices-per-gpu'],
        ARRAY[hrs.model, CAST(hrs.max_slices_per_gpu AS varchar)]
    ) as json) as all_labels,
    CAST({{source_uuid}} AS uuid) as source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    -- Unallocated cost with MIG slice support:
    -- slice_hourly_rate = rate / (days_in_month * 24 * max_slices)
    -- unallocated_cost = slice_hourly_rate * unutilized_slice_hours
    {%- if rate is defined %}
    (CAST({{rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 * hrs.max_slices_per_gpu AS decimal(24,9))) * hrs.unutilized_uptime,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN hrs.model = '{{value | sqlsafe}}'
        THEN (CAST({{value_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 * hrs.max_slices_per_gpu AS decimal(24,9))) * hrs.unutilized_uptime
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 * hrs.max_slices_per_gpu AS decimal(24,9))) * hrs.unutilized_uptime
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    (CAST({{default_rate}} AS decimal(24,9)) / CAST({{amortized_denominator}} * 24 * hrs.max_slices_per_gpu AS decimal(24,9))) * hrs.unutilized_uptime,
    {%- else %}
    0,
    {%- endif %}
    'Tag' AS monthly_cost_type
FROM cte_unutilized_uptime_hours as hrs
WHERE unutilized_uptime > 0
;
