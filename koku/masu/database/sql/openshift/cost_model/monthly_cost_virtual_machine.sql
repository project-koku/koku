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
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    monthly_cost_type,
    cost_category_id
)
SELECT uuid_generate_v4(),
    max(report_period_id) AS report_period_id,
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
    {{rate_type}} AS cost_model_rate_type,
    {%- if rate is defined %}
    {{rate}}::decimal AS cost_model_cpu_cost,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN pod_labels ->> {{ tag_key }} = {{ value }}
        THEN ({{ value_rate }} / {{amortized_denominator}})::decimal
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE ({{ default_rate }} / {{amortized_denominator}})::decimal
        {%- endif %}
    END AS cost_model_cpu_cost,
    {%- elif default_rate is defined %}
    ({{ default_rate }} / {{amortized_denominator}})::decimal as cost_model_cpu_cost,
    {%- else %}
    0::decimal as cost_model_cpu_cost,
    {%- endif %}
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    {{cost_type}} AS monthly_cost_type,
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND all_labels ? 'vm_kubevirt_io_name'
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
    AND monthly_cost_type IS NULL
    {%- if default_rate is defined %}
    AND all_labels ? {{tag_key}}
    {%- elif value_rates is defined %}
    AND (
        {%- for value, value_rate in value_rates.items() %}
        {%- if not loop.first %} OR {%- endif %} pod_labels ->> {{tag_key}} = {{value}}
        {%- endfor %}
    )
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
