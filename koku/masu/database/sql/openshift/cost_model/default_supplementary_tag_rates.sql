-- default_supplementary_tag_rates.sql (Phase 3: RTU INSERT)
--
-- Inserts per-rate tag-based usage costs into rates_to_usage for rows
-- matching a tag key but NOT any of the explicitly-rated tag values.
-- Supplementary cost_model_rate_type is hardcoded.
--
-- Parameters:
--   schema, start_date, end_date, cluster_id, rate, usage_type, metric,
--   tag_key, k_v_pair (list of defined pairs to exclude), labels_field,
--   cost_model_id, rate_uuid, custom_name, source_uuid, report_period_id

INSERT INTO {{schema | sqlsafe}}.rates_to_usage (
    uuid, cost_model_id, report_period_id, source_uuid,
    usage_start, usage_end, node, namespace, cluster_id, cluster_alias,
    data_source, persistentvolumeclaim, pod_labels, volume_labels, all_labels,
    label_hash, custom_name, metric_type, cost_model_rate_type,
    monthly_cost_type, calculated_cost, cost_category_id, rate_id
)
SELECT uuid_generate_v4(),
    {{cost_model_id}},
    report_period_id,
    source_uuid,
    usage_start,
    usage_start,
    node,
    namespace,
    cluster_id,
    cluster_alias,
    data_source,
    persistentvolumeclaim,
    pod_labels,
    volume_labels,
    all_labels,
    encode(sha256(decode(COALESCE(pod_labels::text, '')
        || '|' || COALESCE(volume_labels::text, '')
        || '|' || COALESCE(all_labels::text, ''), 'escape')), 'hex'),
    {{custom_name}},
    {{usage_type}},
    'Supplementary',
    'Tag',
    coalesce({{rate}}::numeric * usage, 0.0),
    cost_category_id,
    {{rate_uuid}}
FROM (
    SELECT lids.report_period_id,
        lids.cluster_id,
        lids.cluster_alias,
        lids.data_source,
        lids.usage_start,
        lids.namespace,
        lids.node,
        lids.resource_id,
        lids.persistentvolumeclaim,
        lids.persistentvolume,
        lids.storageclass,
        lids.source_uuid,
        lids.pod_labels,
        lids.volume_labels,
        lids.all_labels,
        CASE
            WHEN {{metric}}='cpu_core_usage_per_hour' THEN sum(lids.pod_usage_cpu_core_hours)
            WHEN {{metric}}='cpu_core_request_per_hour' THEN sum(lids.pod_request_cpu_core_hours)
            WHEN {{metric}}='cpu_core_effective_usage_per_hour' THEN sum(lids.pod_effective_usage_cpu_core_hours)
            WHEN {{metric}}='memory_gb_usage_per_hour' THEN sum(lids.pod_usage_memory_gigabyte_hours)
            WHEN {{metric}}='memory_gb_request_per_hour' THEN sum(lids.pod_request_memory_gigabyte_hours)
            WHEN {{metric}}='memory_gb_effective_usage_per_hour' THEN sum(lids.pod_effective_usage_memory_gigabyte_hours)
            WHEN {{metric}}='storage_gb_usage_per_month' THEN sum(lids.persistentvolumeclaim_usage_gigabyte_months)
            WHEN {{metric}}='storage_gb_request_per_month' THEN sum(lids.volume_request_storage_gigabyte_months)
        END as usage,
        lids.cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
    WHERE lids.cluster_id = {{cluster_id}}
        AND lids.usage_start >= {{start_date}}
        AND (
            lids.cost_model_rate_type IS NULL
            OR lids.cost_model_rate_type NOT IN ('Infrastructure', 'Supplementary')
        )
        AND lids.usage_start <= {{end_date}}
        AND lids.{{labels_field | sqlsafe}} ? {{tag_key}}
        {% for pair in k_v_pair %}
        AND NOT lids.{{labels_field | sqlsafe}} @> {{pair}}
        {% endfor %}
    GROUP BY lids.report_period_id,
        lids.cluster_id,
        lids.cluster_alias,
        lids.data_source,
        lids.usage_start,
        lids.namespace,
        lids.node,
        lids.resource_id,
        lids.persistentvolumeclaim,
        lids.persistentvolume,
        lids.storageclass,
        lids.source_uuid,
        lids.pod_labels,
        lids.volume_labels,
        lids.all_labels,
        lids.cost_category_id
) AS sub
