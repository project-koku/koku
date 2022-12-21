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
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    source_uuid,
    supplementary_usage_cost,
    {{labels_field | sqlsafe}},
    monthly_cost_type,
    cost_category_id
)
SELECT uuid_generate_v4() as uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_start as usage_end,
    namespace,
    node,
    resource_id,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    source_uuid,
    CASE
        WHEN {{usage_type}} = 'cpu'
            THEN jsonb_build_object('cpu', coalesce(({{rate}}::numeric * usage), 0.0), 'memory', 0.0, 'storage', 0.0)
        WHEN {{usage_type}} = 'memory'
            THEN jsonb_build_object('cpu', 0.0, 'memory', coalesce(({{rate}}::numeric * usage), 0.0), 'storage', 0.0)
        WHEN {{usage_type}} = 'storage'
            THEN jsonb_build_object('cpu', 0.0, 'memory', 0.0, 'storage', coalesce(({{rate}}::numeric * usage), 0.0))
    END as supplementary_usage_cost,
    {{labels_field | sqlsafe}},
    'Tag' as monthly_cost_type, -- We are borrowing the monthly field here, although this is a daily usage cost
    cost_category_id
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
        lids.{{labels_field | sqlsafe}},
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
        lids.{{labels_field | sqlsafe}},
        lids.cost_category_id
) AS sub
