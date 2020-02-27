UPDATE {{schema| sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    SET infrastructure_usage_cost = jsonb_build_object(
        'cpu', {{ infra_cpu_usage_rate }} * pod_usage_cpu_core_hours + {{ infra_cpu_request_rate }} * pod_request_cpu_core_hours,
        'memory', {{ infra_memory_usage_rate }} * pod_usage_memory_gigabyte_hours + {{ infra_memory_request_rate }} * pod_request_memory_gigabyte_hours,
        'storage', {{ infra_storage_usage_rate }} * persistentvolumeclaim_usage_gigabyte_months + {{ infra_storage_request_rate }} * volume_request_storage_gigabyte_months,
    ),
    supplementary_usage_cost = jsonb_build_object(
        'cpu', {{ sup_cpu_usage_rate }} * pod_usage_cpu_core_hours + {{ sup_cpu_request_rate }} * pod_request_cpu_core_hours,
        'memory', {{ sup_memory_usage_rate }} * pod_usage_memory_gigabyte_hours + {{ sup_memory_request_rate }} * pod_request_memory_gigabyte_hours,
        'storage', {{ sup_storage_usage_rate }} * persistentvolumeclaim_usage_gigabyte_months + {{ sup_storage_request_rate }} * volume_request_storage_gigabyte_months,
    )
WHERE cluster_id = {{ cluster_id }}
    AND usage_start BETWEEN {{ start_date }}
        AND {{ end_date }}
;
