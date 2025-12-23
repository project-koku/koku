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
    pod_labels,
    all_labels,
    source_uuid,
    monthly_cost_type,
    cost_model_rate_type,
    cost_model_cpu_cost
)
WITH filtered_data as (
    select
        nsp.namespace,
        {%- if value_rates is defined and value_rates %}
        CASE
            {%- for value, rate in value_rates.items() %}
            WHEN nsp.namespace_labels::json->>'{{ tag_key|sqlsafe }}' = {{value}}
            THEN CAST({{rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}}
            {%- endfor %}
            {%- if default_rate is defined %}
            ELSE CAST({{default_rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}}
            {%- endif %}
        END AS amortized_cost,
        {%- else %}
        CAST({{default_rate}} AS DECIMAL(33, 15)) / {{amortized_denominator}} AS amortized_cost,
        {%- endif %}
        nsp.namespace_labels::json AS filtered_namespace_labels,
        ouds.cluster_id,
        ouds.cluster_alias,
        ouds.node,
        DATE(nsp.interval_start) as usage_start
    from {{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily as nsp
    LEFT JOIN reporting_ocpusagelineitem_daily_summary as ouds
        ON nsp.month = lpad(ouds.month, 2, '0')
        AND nsp.year = ouds.year
        AND nsp.source = ouds.source
        AND nsp.namespace = ouds.namespace
        AND DATE(nsp.interval_start) = DATE(ouds.usage_start)
    WHERE nsp.month = {{month}}
        and nsp.year = {{year}}
        and nsp.source = {{source_uuid | string}}
        and nsp.namespace NOT LIKE 'kube-%'
        and nsp.namespace NOT LIKE 'openshift-%'
        and nsp.namespace != 'openshift'
        and DATE(nsp.interval_start) >= DATE({{start_date}})
        and DATE(nsp.interval_start) <= DATE({{end_date}})
        {%- if default_rate is defined %}
            AND nsp.namespace_labels::json->'{{ tag_key|sqlsafe }}' IS NOT NULL
        {%- else %}
            AND (
                {%- for value, rate in value_rates.items() %}
                    {%- if not loop.first %} OR {%- endif %} nsp.namespace_labels::json->>'{{ tag_key|sqlsafe }}' = {{value}}
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
    DATE(nsp.interval_start)
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
    {{report_period_id}} AS report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Pod' as data_source,
    fd.usage_start,
    fd.usage_start as usage_end,
    fd.namespace,
    fd.node,
    fd.filtered_namespace_labels as pod_labels,
    fd.filtered_namespace_labels as all_labels,
    {{source_uuid}}::uuid,
    'Tag' AS monthly_cost_type,
    {{rate_type}} AS cost_model_rate_type,
    CASE
        WHEN nc.node_count < 1
        THEN fd.amortized_cost
        ELSE fd.amortized_cost / nc.node_count
    END
FROM filtered_data as fd
JOIN node_count as nc
    ON fd.namespace = nc.namespace
    AND fd.usage_start = nc.usage_start;
