-- insert_usage_rates_to_usage.sql (Phase 2)
--
-- Deletes stale rows then writes per-rate cost rows to rates_to_usage
-- in a single pass (both Infrastructure and Supplementary cost types).
--
-- RatesToUsage is the single source of truth — daily summary is populated
-- via aggregation from this table (see aggregate_rates_to_daily_summary.sql).
--
-- Rate values (default_rate), cost_type, and custom_name are read directly
-- from cost_model_rate via the rate_names CTE, eliminating per-metric Jinja
-- parameters.  The only rate-value param remaining is cluster_cost_per_hour
-- which is needed for the cte_node_cost pre-computation.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   distribution, cost_model_id, cluster_cost_per_hour

DELETE FROM {{schema | sqlsafe}}.rates_to_usage
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}};

WITH cte_node_cost AS (
    SELECT
        usage_start,
        node,
        sum(pod_effective_usage_cpu_core_hours) AS node_cpu_usage,
        sum(pod_effective_usage_memory_gigabyte_hours) AS node_mem_usage,
        CASE WHEN {{distribution}} = 'cpu' THEN
            coalesce(max(node_capacity_cpu_core_hours) / nullif(max(cluster_capacity_cpu_core_hours), 0), 0)
            * coalesce(max(node_capacity_cpu_core_hours) / nullif(max(node_capacity_cpu_cores), 0), 0)
            * {{cluster_cost_per_hour}}
        ELSE 0
        END AS node_cluster_hour_cost_cpu_per_day,
        CASE WHEN {{distribution}} = 'memory' THEN
            coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(cluster_capacity_memory_gigabyte_hours), 0), 0)
            * coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(node_capacity_memory_gigabytes), 0), 0)
            * {{cluster_cost_per_hour}}
        ELSE 0
        END AS node_cluster_hour_cost_mem_per_day
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= {{start_date}}
        AND usage_start <= {{end_date}}
        AND source_uuid = {{source_uuid}}
        AND node IS NOT NULL
        AND node != ''
        AND (cost_model_rate_type IS NULL
             OR cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
    GROUP BY usage_start, node
),

base AS (
    SELECT
        lids.usage_start,
        lids.cluster_id,
        max(lids.cluster_alias) AS cluster_alias,
        lids.node,
        lids.namespace,
        lids.data_source,
        lids.persistentvolumeclaim,
        lids.pod_labels,
        lids.volume_labels,
        lids.all_labels,
        md5(COALESCE(lids.pod_labels::text, '')
            || COALESCE(lids.volume_labels::text, '')
            || COALESCE(lids.all_labels::text, '')) AS label_hash,
        lids.cost_category_id,

        sum(coalesce(lids.pod_usage_cpu_core_hours, 0)) AS cpu_usage_hours,
        sum(coalesce(lids.pod_request_cpu_core_hours, 0)) AS cpu_request_hours,
        sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) AS cpu_effective_hours,

        {%- if distribution == 'cpu' %}
        sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) AS node_alloc_basis,
        sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) AS cluster_alloc_basis,
        {%- else %}
        coalesce(
            sum(lids.pod_effective_usage_memory_gigabyte_hours)
            / nullif(max(lids.node_capacity_memory_gigabyte_hours), 0)
            * max(lids.node_capacity_cpu_core_hours),
        0) AS node_alloc_basis,
        coalesce(
            sum(lids.pod_effective_usage_memory_gigabyte_hours)
            / nullif(max(lids.node_capacity_memory_gigabyte_hours), 0)
            * max(lids.node_capacity_cpu_core_hours),
        0) AS cluster_alloc_basis,
        {%- endif %}

        coalesce(
            sum(lids.pod_effective_usage_cpu_core_hours::decimal)
            / nullif(max(cnc.node_cpu_usage::decimal), 0)
            * max(cnc.node_cluster_hour_cost_cpu_per_day::decimal),
        0) AS cluster_hourly_cpu_cost,

        coalesce(
            sum(lids.pod_effective_usage_memory_gigabyte_hours::decimal)
            / nullif(max(cnc.node_mem_usage::decimal), 0)
            * max(cnc.node_cluster_hour_cost_mem_per_day::decimal),
        0) AS cluster_hourly_mem_cost,

        sum(coalesce(lids.pod_usage_memory_gigabyte_hours, 0)) AS mem_usage_hours,
        sum(coalesce(lids.pod_request_memory_gigabyte_hours, 0)) AS mem_request_hours,
        sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0)) AS mem_effective_hours,

        sum(coalesce(lids.persistentvolumeclaim_usage_gigabyte_months, 0)) AS storage_usage_months,
        sum(coalesce(lids.volume_request_storage_gigabyte_months, 0)) AS storage_request_months

    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    LEFT JOIN cte_node_cost AS cnc
        ON lids.usage_start = cnc.usage_start
        AND lids.node = cnc.node
    WHERE lids.usage_start >= {{start_date}}
        AND lids.usage_start <= {{end_date}}
        AND lids.source_uuid = {{source_uuid}}
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace IS NOT NULL
        AND (lids.cost_model_rate_type IS NULL
             OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary'))
    GROUP BY
        lids.usage_start,
        lids.cluster_id,
        lids.node,
        lids.namespace,
        lids.data_source,
        lids.persistentvolumeclaim,
        lids.pod_labels,
        lids.volume_labels,
        lids.all_labels,
        lids.cost_category_id
),

rate_names AS (
    SELECT r.uuid AS rate_uuid, r.custom_name, r.metric,
           r.default_rate, r.cost_type
    FROM {{schema | sqlsafe}}.cost_model_rate r
    JOIN {{schema | sqlsafe}}.price_list pl ON r.price_list_id = pl.uuid
    JOIN {{schema | sqlsafe}}.price_list_cost_model_map pcm ON pcm.price_list_id = pl.uuid
    WHERE pcm.cost_model_id = {{cost_model_id}}
      AND r.default_rate IS NOT NULL
      AND r.default_rate != 0
)

INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id, rate_id
)

-- Component 1: cpu_core_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'cpu_core_usage_per_hour'), 'cpu', rn.cost_type,
    NULL, b.cpu_usage_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_usage_per_hour'

UNION ALL

-- Component 2: cpu_core_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'cpu_core_request_per_hour'), 'cpu', rn.cost_type,
    NULL, b.cpu_request_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_request_per_hour'

UNION ALL

-- Component 3: cpu_core_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'cpu_core_effective_usage_per_hour'), 'cpu', rn.cost_type,
    NULL, b.cpu_effective_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_effective_usage_per_hour'

UNION ALL

-- Component 4: node_core_cost_per_hour (always cpu, distribution affects usage basis)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'node_core_cost_per_hour'), 'cpu', rn.cost_type,
    NULL, b.node_alloc_basis * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'node_core_cost_per_hour'

UNION ALL

-- Component 5: cluster_core_cost_per_hour (always cpu, distribution affects usage basis)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'cluster_core_cost_per_hour'), 'cpu', rn.cost_type,
    NULL, b.cluster_alloc_basis * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cluster_core_cost_per_hour'

UNION ALL

-- Component 6: cluster_cost_per_hour via CTE (metric_type is distribution-dependent)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'cluster_cost_per_hour'),
    {%- if distribution == 'cpu' %}
    'cpu',
    {%- else %}
    'memory',
    {%- endif %}
    rn.cost_type,
    NULL,
    {%- if distribution == 'cpu' %}
    b.cluster_hourly_cpu_cost,
    {%- else %}
    b.cluster_hourly_mem_cost,
    {%- endif %}
    b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cluster_cost_per_hour'

UNION ALL

-- Component 7: memory_gb_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'memory_gb_usage_per_hour'), 'memory', rn.cost_type,
    NULL, b.mem_usage_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_usage_per_hour'

UNION ALL

-- Component 8: memory_gb_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'memory_gb_request_per_hour'), 'memory', rn.cost_type,
    NULL, b.mem_request_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_request_per_hour'

UNION ALL

-- Component 9: memory_gb_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'memory_gb_effective_usage_per_hour'), 'memory', rn.cost_type,
    NULL, b.mem_effective_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_effective_usage_per_hour'

UNION ALL

-- Component 10: storage_gb_usage_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'storage_gb_usage_per_month'), 'storage', rn.cost_type,
    NULL, b.storage_usage_months * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'storage_gb_usage_per_month'

UNION ALL

-- Component 11: storage_gb_request_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, 'storage_gb_request_per_month'), 'storage', rn.cost_type,
    NULL, b.storage_request_months * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'storage_gb_request_per_month'
;
