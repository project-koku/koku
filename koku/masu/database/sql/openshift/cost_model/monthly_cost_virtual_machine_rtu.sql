-- monthly_cost_virtual_machine.sql (Phase 3: RTU INSERT)
--
-- Inserts monthly OCP_VM costs into rates_to_usage.
-- Supports flat rate, per-tag-value rates, and default rate patterns.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   rate (optional), cost_type, rate_type, cost_model_id,
--   rate_uuid, custom_name, tag_key (optional), value_rates (optional),
--   default_rate (optional), amortized_denominator (optional)

INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id, rate_id
)
SELECT uuid_generate_v4(),
    {{cost_model_id}},
    max(report_period_id),
    source_uuid,
    usage_start,
    usage_end,
    node,
    lids.namespace,
    cluster_id,
    cluster_alias,
    data_source,
    NULL,
    pod_labels,
    NULL::jsonb,
    all_labels,
    encode(sha256(decode(COALESCE(pod_labels::text, '') || '|' || '|' || COALESCE(all_labels::text, ''), 'escape')), 'hex'),
    {{custom_name}},
    {{metric_type}},
    {{rate_type}},
    {{cost_type}},
    {%- if rate is defined %}
    {{rate}}::decimal,
    {%- elif value_rates is defined %}
    CASE
        {%- for value, value_rate in value_rates.items() %}
        WHEN pod_labels ->> {{ tag_key }} = {{ value }}
        THEN ({{ value_rate }} / {{amortized_denominator}})::decimal
        {%- endfor %}
        {%- if default_rate is defined %}
        ELSE ({{ default_rate }} / {{amortized_denominator}})::decimal
        {%- endif %}
    END,
    {%- elif default_rate is defined %}
    ({{ default_rate }} / {{amortized_denominator}})::decimal,
    {%- else %}
    0::decimal,
    {%- endif %}
    cost_category_id,
    {{rate_uuid}}
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND all_labels ? 'vm_kubevirt_io_name'
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
    AND monthly_cost_type IS NULL
    AND (
        lids.cost_model_rate_type IS NULL
        OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
    )
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
