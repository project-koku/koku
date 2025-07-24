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
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_model_rate_type,
    {{labels_field | sqlsafe}},
    all_labels,
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
            THEN coalesce(({{rate}}::numeric * usage), 0.0)
        ELSE 0.0
    END as cost_model_cpu_cost,
    CASE
        WHEN {{usage_type}} = 'memory'
            THEN coalesce(({{rate}}::numeric * usage), 0.0)
        ELSE 0.0
    END as cost_model_memory_cost,
    CASE
        WHEN {{usage_type}} = 'storage'
            THEN coalesce(({{rate}}::numeric * usage), 0.0)
        ELSE 0.0
    END as cost_model_volume_cost,
    'Supplementary' as cost_model_rate_type,
    {{labels_field | sqlsafe}},
    {{labels_field | sqlsafe}} as all_labels,
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
        lids.{{labels_field | sqlsafe}},
        lids.cost_category_id
) AS sub
