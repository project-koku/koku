-- insert_usage_rates_to_usage.sql (Phase 2)
--
-- Deletes stale rows then writes per-rate cost rows to rates_to_usage
-- in a single pass (both Infrastructure and Supplementary cost types).
--
-- RatesToUsage is the single source of truth — daily summary is populated
-- via aggregation from this table (see aggregate_rates_to_daily_summary.sql).
--
-- Rate values (default_rate), cost_type, and custom_name are read directly
-- from cost_model_rate via the rate_names CTE, eliminating all per-metric
-- Jinja parameters.  cte_node_cost computes allocation fractions only;
-- the actual rate multiplication happens in Component 6 via rn.default_rate
-- so each cost_type (Infrastructure / Supplementary) gets its own rate.
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   cost_model_id

DELETE FROM {{schema | sqlsafe}}.rates_to_usage
WHERE usage_start >= {{start_date}}
  AND usage_start <= {{end_date}}
  AND source_uuid = {{source_uuid}}
  AND report_period_id = {{report_period_id}};

WITH cost_model_info AS (
    SELECT coalesce(cm.distribution_info->>'distribution_type', cm.distribution, 'cpu') AS distribution
    FROM {{schema | sqlsafe}}.cost_model cm
    WHERE cm.uuid = {{cost_model_id}}
),

cte_node_cost AS (
    SELECT
        usage_start,
        node,
        sum(pod_effective_usage_cpu_core_hours) AS node_cpu_usage,
        sum(pod_effective_usage_memory_gigabyte_hours) AS node_mem_usage,
        CASE WHEN cmi.distribution = 'cpu' THEN
            coalesce(max(node_capacity_cpu_core_hours) / nullif(max(cluster_capacity_cpu_core_hours), 0), 0)
            * coalesce(max(node_capacity_cpu_core_hours) / nullif(max(node_capacity_cpu_cores), 0), 0)
        ELSE 0
        END AS node_cluster_fraction_cpu,
        CASE WHEN cmi.distribution = 'memory' THEN
            coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(cluster_capacity_memory_gigabyte_hours), 0), 0)
            * coalesce(max(node_capacity_memory_gigabyte_hours) / nullif(max(node_capacity_memory_gigabytes), 0), 0)
        ELSE 0
        END AS node_cluster_fraction_mem
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    CROSS JOIN cost_model_info cmi
    WHERE usage_start >= {{start_date}}
        AND usage_start <= {{end_date}}
        AND source_uuid = {{source_uuid}}
        AND node IS NOT NULL
        AND node != ''
        AND cost_model_rate_type IS NULL
    GROUP BY usage_start, node, cmi.distribution
),

base AS (
    SELECT
        cmi.distribution,
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
            || '|' || COALESCE(lids.volume_labels::text, '')
            || '|' || COALESCE(lids.all_labels::text, '')) AS label_hash,
        lids.cost_category_id,

        sum(coalesce(lids.pod_usage_cpu_core_hours, 0)) AS cpu_usage_hours,
        sum(coalesce(lids.pod_request_cpu_core_hours, 0)) AS cpu_request_hours,
        sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0)) AS cpu_effective_hours,

        CASE WHEN cmi.distribution = 'cpu' THEN
            sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0))
        ELSE
            coalesce(
                sum(lids.pod_effective_usage_memory_gigabyte_hours)
                / nullif(max(lids.node_capacity_memory_gigabyte_hours), 0)
                * max(lids.node_capacity_cpu_core_hours),
            0)
        END AS node_alloc_basis,
        CASE WHEN cmi.distribution = 'cpu' THEN
            sum(coalesce(lids.pod_effective_usage_cpu_core_hours, 0))
        ELSE
            coalesce(
                sum(lids.pod_effective_usage_memory_gigabyte_hours)
                / nullif(max(lids.node_capacity_memory_gigabyte_hours), 0)
                * max(lids.node_capacity_cpu_core_hours),
            0)
        END AS cluster_alloc_basis,

        coalesce(
            sum(lids.pod_effective_usage_cpu_core_hours::decimal)
            / nullif(max(cnc.node_cpu_usage::decimal), 0)
            * max(cnc.node_cluster_fraction_cpu::decimal),
        0) AS cluster_hourly_cpu_fraction,

        coalesce(
            sum(lids.pod_effective_usage_memory_gigabyte_hours::decimal)
            / nullif(max(cnc.node_mem_usage::decimal), 0)
            * max(cnc.node_cluster_fraction_mem::decimal),
        0) AS cluster_hourly_mem_fraction,

        sum(coalesce(lids.pod_usage_memory_gigabyte_hours, 0)) AS mem_usage_hours,
        sum(coalesce(lids.pod_request_memory_gigabyte_hours, 0)) AS mem_request_hours,
        sum(coalesce(lids.pod_effective_usage_memory_gigabyte_hours, 0)) AS mem_effective_hours,

        sum(coalesce(lids.persistentvolumeclaim_usage_gigabyte_months, 0)) AS storage_usage_months,
        sum(coalesce(lids.volume_request_storage_gigabyte_months, 0)) AS storage_request_months

    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    CROSS JOIN cost_model_info cmi
    LEFT JOIN cte_node_cost AS cnc
        ON lids.usage_start = cnc.usage_start
        AND lids.node = cnc.node
    WHERE lids.usage_start >= {{start_date}}
        AND lids.usage_start <= {{end_date}}
        AND lids.source_uuid = {{source_uuid}}
        AND lids.report_period_id = {{report_period_id}}
        AND lids.namespace IS NOT NULL
        AND lids.cost_model_rate_type IS NULL
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
        lids.cost_category_id,
        cmi.distribution
),

rate_names AS (
    SELECT r.uuid AS rate_uuid, r.custom_name, r.metric,
           r.metric_type, r.default_rate, r.cost_type
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
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.cpu_usage_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_usage_per_hour'

UNION ALL

-- Component 2: cpu_core_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.cpu_request_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_request_per_hour'

UNION ALL

-- Component 3: cpu_core_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.cpu_effective_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cpu_core_effective_usage_per_hour'

UNION ALL

-- Component 4: node_core_cost_per_hour
-- metric_type forced to 'cpu': Rate table stores 'node' but aggregation routes
-- costs via metric_type IN ('cpu','memory','storage') into cost_model_*_cost columns.
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), 'cpu', rn.cost_type,
    NULL, b.node_alloc_basis * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'node_core_cost_per_hour'

UNION ALL

-- Component 5: cluster_core_cost_per_hour
-- metric_type forced to 'cpu': same reason as Component 4.
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), 'cpu', rn.cost_type,
    NULL, b.cluster_alloc_basis * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cluster_core_cost_per_hour'

UNION ALL

-- Component 6: cluster_cost_per_hour via CTE (metric_type is distribution-dependent)
-- Fraction is pre-computed in cte_node_cost → base; rate applied here per cost_type.
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric),
    CASE WHEN b.distribution = 'cpu' THEN 'cpu' ELSE 'memory' END,
    rn.cost_type,
    NULL,
    CASE WHEN b.distribution = 'cpu'
        THEN b.cluster_hourly_cpu_fraction * rn.default_rate
        ELSE b.cluster_hourly_mem_fraction * rn.default_rate
    END,
    b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'cluster_cost_per_hour'

UNION ALL

-- Component 7: memory_gb_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.mem_usage_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_usage_per_hour'

UNION ALL

-- Component 8: memory_gb_request_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.mem_request_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_request_per_hour'

UNION ALL

-- Component 9: memory_gb_effective_usage_per_hour
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.mem_effective_hours * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'memory_gb_effective_usage_per_hour'

UNION ALL

-- Component 10: storage_gb_usage_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.storage_usage_months * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'storage_gb_usage_per_month'

UNION ALL

-- Component 11: storage_gb_request_per_month
SELECT uuid_generate_v4(), {{cost_model_id}}, {{report_period_id}}, {{source_uuid}},
    b.usage_start, b.usage_start, b.node, b.namespace, b.cluster_id, b.cluster_alias,
    b.data_source, b.persistentvolumeclaim, b.pod_labels, b.volume_labels, b.all_labels, b.label_hash,
    COALESCE(rn.custom_name, rn.metric), rn.metric_type, rn.cost_type,
    NULL, b.storage_request_months * rn.default_rate, b.cost_category_id, rn.rate_uuid
FROM base b INNER JOIN rate_names rn ON rn.metric = 'storage_gb_request_per_month'
;
