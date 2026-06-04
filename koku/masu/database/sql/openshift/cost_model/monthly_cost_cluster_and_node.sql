-- monthly_cost_cluster_and_node.sql (Phase 3: RTU INSERT)
--
-- Inserts monthly Node/Cluster/Node_Core_Month costs into rates_to_usage.
-- Cost is distributed across pods based on effective usage relative to
-- node or cluster capacity, routed by distribution type (cpu or memory).
--
-- Parameters:
--   schema, start_date, end_date, source_uuid, report_period_id,
--   rate, cost_type, rate_type, distribution, cost_model_id,
--   rate_uuid, custom_name

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
    max(usage_end),
    node,
    lids.namespace,
    cluster_id,
    max(cluster_alias),
    'Pod',
    NULL,
    pod_labels,
    NULL::jsonb,
    pod_labels::jsonb,
    encode(sha256(decode(COALESCE(pod_labels::text, '') || '|' || '|' || COALESCE(pod_labels::text, ''), 'escape')), 'hex'),
    {{custom_name}},
    {{metric_type}},
    {{rate_type}},
    {{cost_type}},
    CASE
        WHEN {{cost_type}} = 'Cluster' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(cluster_capacity_cpu_core_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node_Core_Month' AND {{distribution}} = 'cpu'
            THEN sum(pod_effective_usage_cpu_core_hours) / max(node_capacity_cpu_core_hours) * max(node_capacity_cpu_cores) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Cluster' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(cluster_capacity_memory_gigabyte_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * {{rate}}::decimal
        WHEN {{cost_type}} = 'Node_Core_Month' AND {{distribution}} = 'memory'
            THEN sum(pod_effective_usage_memory_gigabyte_hours) / max(node_capacity_memory_gigabyte_hours) * max(node_capacity_cpu_cores) * {{rate}}::decimal
        ELSE 0
    END,
    cost_category_id,
    {{rate_uuid}}
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id}}
    AND namespace IS NOT NULL
    AND data_source = 'Pod'
    AND monthly_cost_type IS NULL
    AND node_capacity_cpu_core_hours IS NOT NULL
    AND node_capacity_cpu_core_hours != 0
    AND cluster_capacity_cpu_core_hours IS NOT NULL
    AND cluster_capacity_cpu_core_hours != 0
    AND (
            lids.cost_model_rate_type IS NULL
            OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
        )
GROUP BY usage_start, source_uuid, cluster_id, node, namespace, pod_labels, cost_category_id
;
