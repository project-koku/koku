UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
SET infrastructure_usage_cost = other_sub.infrastructure_usage_cost
FROM (
    SELECT sub.uuid,
        jsonb_object_agg(key,
            CASE
            WHEN key = {{usage_type}} THEN value::numeric + coalesce(({{rate}}::numeric * usage), 0.0)
            ELSE value::numeric
            END) as infrastructure_usage_cost
    FROM (
        SELECT lids.uuid,
            key,
            value,
            CASE
            WHEN {{metric}}='cpu_core_usage_per_hour' THEN lids.pod_usage_cpu_core_hours
            WHEN {{metric}}='cpu_core_request_per_hour' THEN lids.pod_request_cpu_core_hours
            WHEN {{metric}}='cpu_core_effective_usage_per_hour' THEN lids.pod_effective_usage_cpu_core_hours
            WHEN {{metric}}='memory_gb_usage_per_hour' THEN lids.pod_usage_memory_gigabyte_hours
            WHEN {{metric}}='memory_gb_request_per_hour' THEN lids.pod_request_memory_gigabyte_hours
            WHEN {{metric}}='memory_gb_effective_usage_per_hour' THEN lids.pod_effective_usage_memory_gigabyte_hours
            WHEN {{metric}}='storage_gb_usage_per_month' THEN lids.persistentvolumeclaim_usage_gigabyte_months
            WHEN {{metric}}='storage_gb_request_per_month' THEN lids.volume_request_storage_gigabyte_months
            END as usage
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids,
            jsonb_each_text(lids.infrastructure_usage_cost) infrastructure_usage_cost
        WHERE lids.cluster_id = {{cluster_id}}
            AND lids.usage_start >= {{start_date}}
            AND lids.usage_start <= {{end_date}}
            AND lids.{{labels_field | sqlsafe}} ? {{tag_key}}
            {% for pair in k_v_pair %}
            AND NOT lids.{{labels_field | sqlsafe}} @> {{pair}}
            {% endfor %}
    ) AS sub
    GROUP BY sub.uuid
) other_sub
WHERE lids.uuid = other_sub.uuid
