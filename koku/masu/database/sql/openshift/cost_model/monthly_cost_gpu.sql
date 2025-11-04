DELETE FROM {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND cost_model_rate_type = {{rate_type}};

INSERT INTO {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p (
    id,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    pod,
    usage_start,
    usage_end,
    gpu_vendor_name,
    gpu_model_name,
    gpu_memory_capacity_mib,
    gpu_pod_uptime,
    gpu_count,
    source_uuid,
    gpu_cost,
    cost_model_rate_type,
    cost_category_id
)
SELECT uuid_generate_v4() as id,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    pod,
    usage_start,
    usage_end,
    gpu_vendor_name,
    gpu_model_name,
    gpu_memory_capacity_mib,
    gpu_pod_uptime,
    gpu_count,
    source_uuid,
    {%- if rate is defined %}
    {{rate}}::decimal as gpu_cost,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN gpu_model_name = {{ value }}
        THEN ({{ value_rate }} / {{amortized_denominator}})::decimal
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE ({{ default_rate }} / {{amortized_denominator}})::decimal
        {%- endif %}
    END as gpu_cost,
    {%- elif default_rate is defined %}
    ({{ default_rate }} / {{amortized_denominator}})::decimal as gpu_cost,
    {%- else %}
    0::decimal as gpu_cost,
    {%- endif %}
    {{rate_type}} as cost_model_rate_type,
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocp_gpu_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND gpu_model_name IS NOT NULL
    AND cost_model_rate_type IS NULL;
