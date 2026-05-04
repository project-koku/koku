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
WITH filtered_data as (
    select
        nsp.namespace,
        {%- if value_rates is defined and value_rates %}
        CASE
            {%- for value, rate in value_rates.items() %}
            WHEN nsp.namespace_labels::jsonb->>'{{ tag_key|sqlsafe }}' = {{value}}
            THEN CAST({{rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}}
            {%- endfor %}
            {%- if default_rate is defined %}
            ELSE CAST({{default_rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}}
            {%- endif %}
        END AS amortized_cost,
        {%- else %}
        CAST({{default_rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}} AS amortized_cost,
        {%- endif %}
        nsp.namespace_labels::jsonb AS filtered_namespace_labels,
        ouds.cluster_id,
        ouds.cluster_alias,
        ouds.node,
        nsp.usage_start
    from {{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily as nsp
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging as ouds
        ON nsp.month = lpad(ouds.month, 2, '0')
        AND nsp.year = ouds.year
        AND nsp.source = ouds.source
        AND nsp.namespace = ouds.namespace
        AND nsp.usage_start = DATE(ouds.usage_start)
    WHERE nsp.month = {{month}}
        and nsp.year = {{year}}
        and nsp.source = {{source_uuid | string}}
        and nsp.namespace NOT LIKE 'kube-%%'
        and nsp.namespace NOT LIKE 'openshift-%%'
        and nsp.namespace != 'openshift'
        and nsp.usage_start >= DATE({{start_date}})
        and nsp.usage_start <= DATE({{end_date}})
        {%- if default_rate is defined %}
            AND nsp.namespace_labels::jsonb->>'{{ tag_key|sqlsafe }}' IS NOT NULL
        {%- else %}
            AND (
                {%- for value, rate in value_rates.items() %}
                    {%- if not loop.first %} OR {%- endif %} nsp.namespace_labels::jsonb->>'{{ tag_key|sqlsafe }}' = {{value}}
                {%- if loop.last %} ) {%- endif %}
                {%- endfor %}
        {%- endif %}
    GROUP by
    2,
    3,
    nsp.namespace,
    ouds.cluster_id,
    ouds.cluster_alias,
    ouds.node,
    nsp.usage_start
),
node_count as (
    select
        namespace,
        CAST(count(node) AS DECIMAL(33, 15)) as node_count,
        usage_start
    from filtered_data
    group by namespace, usage_start
)
SELECT
    uuid_generate_v4(),
    {{cost_model_id}} AS cost_model_id,
    {{report_period_id}} AS report_period_id,
    {{source_uuid}}::uuid,
    fd.usage_start,
    fd.usage_start as usage_end,
    fd.node,
    fd.namespace,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Pod' as data_source,
    NULL AS persistentvolumeclaim,
    fd.filtered_namespace_labels as pod_labels,
    NULL::jsonb AS volume_labels,
    fd.filtered_namespace_labels as all_labels,
    md5(COALESCE(fd.filtered_namespace_labels::text, '') || '|' || COALESCE((NULL::jsonb)::text, '') || '|' || COALESCE(fd.filtered_namespace_labels::text, '')) AS label_hash,
    {{custom_name}} AS custom_name,
    'cpu' AS metric_type,
    {{rate_type}} AS cost_model_rate_type,
    'Tag' AS monthly_cost_type,
    CASE
        WHEN nc.node_count < 1
        THEN fd.amortized_cost
        ELSE fd.amortized_cost / nc.node_count
    END AS calculated_cost,
    NULL AS cost_category_id,
    {{rate_uuid}} AS rate_id
FROM filtered_data as fd
JOIN node_count as nc
    ON fd.namespace = nc.namespace
    AND fd.usage_start = nc.usage_start
RETURNING 1;
