-- insert_usage_rates_to_usage.sql (Phase 2 PoC)
--
-- Writes per-rate cost rows to cost_model_rates_to_usage.
-- REPLACES usage_costs.sql direct-write. RatesToUsage is the single
-- source of truth — daily summary is populated via aggregation from
-- this table (see aggregate_rates_to_daily_summary.sql).
--
-- GROUP BY matches usage_costs.sql exactly (including pod_labels,
-- volume_labels, persistentvolumeclaim, all_labels) so the aggregation
-- step can produce daily summary rows at the correct granularity.
--
-- IQ-2: cluster_cost_per_hour metric_type is set dynamically via Jinja
-- conditional, matching the existing pattern in usage_costs.sql.
--
-- IQ-5: Single SQL statement — CTE + INSERT with UNION ALL. Works with
-- _prepare_and_execute_raw_sql_query (no multi-statement support needed).
--
-- Parameters (same as usage_costs.sql plus cost_model_id):
--   schema, start_date, end_date, source_uuid, report_period_id,
--   rate_type, distribution, cost_model_id,
--   cpu_core_usage_per_hour, cpu_core_request_per_hour,
--   cpu_core_effective_usage_per_hour, node_core_cost_per_hour,
--   cluster_core_cost_per_hour, cluster_cost_per_hour,
--   memory_gb_usage_per_hour, memory_gb_request_per_hour,
--   memory_gb_effective_usage_per_hour,
--   storage_gb_usage_per_month, storage_gb_request_per_month

DELETE FROM {{schema | sqlsafe}}.cost_model_rates_to_usage AS rtu
WHERE rtu.usage_start >= {{start_date}}
    AND rtu.usage_start <= {{end_date}}
    AND rtu.source_uuid = {{source_uuid}}
    AND rtu.report_period_id = {{report_period_id}}
    AND rtu.cost_model_rate_type = {{rate_type}}
    AND rtu.monthly_cost_type IS NULL
;

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

        -- CPU usage aggregates
        sum(coalesce(lids.pod_usage_cpu_core_hours, 0)) AS cpu_usage_hours,
        sum(coalesce(lids.pod_request_cpu_core_hours, 0)) AS cpu_request_hours,
        sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) AS cpu_effective_hours,

        -- Node/cluster core allocation (distribution-dependent basis, always → cpu cost)
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

        -- Cluster hourly cost via CTE (split by distribution)
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

        -- Memory usage aggregates
        sum(coalesce(lids.pod_usage_memory_gigabyte_hours, 0)) AS mem_usage_hours,
        sum(coalesce(lids.pod_request_memory_gigabyte_hours, 0)) AS mem_request_hours,
        sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0)) AS mem_effective_hours,

        -- Storage usage aggregates
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
)

INSERT INTO {{schema | sqlsafe}}.cost_model_rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id
)

-- Component 1: cpu_core_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'cpu_core_usage_per_hour', 'cpu', {{rate_type}},
    NULL, b.cpu_usage_hours * {{cpu_core_usage_per_hour}}, b.cost_category_id
FROM base b WHERE {{cpu_core_usage_per_hour}} != 0

UNION ALL

-- Component 2: cpu_core_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'cpu_core_request_per_hour', 'cpu', {{rate_type}},
    NULL, b.cpu_request_hours * {{cpu_core_request_per_hour}}, b.cost_category_id
FROM base b WHERE {{cpu_core_request_per_hour}} != 0

UNION ALL

-- Component 3: cpu_core_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'cpu_core_effective_usage_per_hour', 'cpu', {{rate_type}},
    NULL, b.cpu_effective_hours * {{cpu_core_effective_usage_per_hour}}, b.cost_category_id
FROM base b WHERE {{cpu_core_effective_usage_per_hour}} != 0

UNION ALL

-- Component 4: node_core_cost_per_hour (always cpu, distribution affects usage basis)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'node_core_cost_per_hour', 'cpu', {{rate_type}},
    NULL, b.node_alloc_basis * {{node_core_cost_per_hour}}, b.cost_category_id
FROM base b WHERE {{node_core_cost_per_hour}} != 0

UNION ALL

-- Component 5: cluster_core_cost_per_hour (always cpu, distribution affects usage basis)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'cluster_core_cost_per_hour', 'cpu', {{rate_type}},
    NULL, b.cluster_alloc_basis * {{cluster_core_cost_per_hour}}, b.cost_category_id
FROM base b WHERE {{cluster_core_cost_per_hour}} != 0

UNION ALL

-- Component 6: cluster_cost_per_hour via CTE
-- IQ-2: metric_type is distribution-dependent (same Jinja pattern as cte_node_cost)
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'cluster_cost_per_hour',
    {%- if distribution == 'cpu' %}
    'cpu',
    {%- else %}
    'memory',
    {%- endif %}
    {{rate_type}},
    NULL,
    {%- if distribution == 'cpu' %}
    b.cluster_hourly_cpu_cost,
    {%- else %}
    b.cluster_hourly_mem_cost,
    {%- endif %}
    b.cost_category_id
FROM base b WHERE {{cluster_cost_per_hour}} != 0

UNION ALL

-- Component 7: memory_gb_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'memory_gb_usage_per_hour', 'memory', {{rate_type}},
    NULL, b.mem_usage_hours * {{memory_gb_usage_per_hour}}, b.cost_category_id
FROM base b WHERE {{memory_gb_usage_per_hour}} != 0

UNION ALL

-- Component 8: memory_gb_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'memory_gb_request_per_hour', 'memory', {{rate_type}},
    NULL, b.mem_request_hours * {{memory_gb_request_per_hour}}, b.cost_category_id
FROM base b WHERE {{memory_gb_request_per_hour}} != 0

UNION ALL

-- Component 9: memory_gb_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'memory_gb_effective_usage_per_hour', 'memory', {{rate_type}},
    NULL, b.mem_effective_hours * {{memory_gb_effective_usage_per_hour}}, b.cost_category_id
FROM base b WHERE {{memory_gb_effective_usage_per_hour}} != 0

UNION ALL

-- Component 10: storage_gb_usage_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'storage_gb_usage_per_month', 'storage', {{rate_type}},
    NULL, b.storage_usage_months * {{storage_gb_usage_per_month}}, b.cost_category_id
FROM base b WHERE {{storage_gb_usage_per_month}} != 0

UNION ALL

-- Component 11: storage_gb_request_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    'storage_gb_request_per_month', 'storage', {{rate_type}},
    NULL, b.storage_request_months * {{storage_gb_request_per_month}}, b.cost_category_id
FROM base b WHERE {{storage_gb_request_per_month}} != 0
;
