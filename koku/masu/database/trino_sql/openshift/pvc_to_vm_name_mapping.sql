WITH cte_mappings as (
    SELECT
        storage.persistentvolumeclaim,
        vm.vm_name
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS pod_usage
    INNER JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as storage
        ON pod_usage.pod = storage.pod
        AND pod_usage.year = storage.year
        AND pod_usage.month = storage.month
        AND pod_usage.source = storage.source
    INNER JOIN (
        select
            vm_name,
            CONCAT('vm_kubevirt_io_name": "', vm_name) as substring
        from postgres.{{schema | sqlsafe}}.reporting_ocp_vm_summary_p
        WHERE usage_start >= DATE({{start_date | string}})
            AND usage_start <= DATE({{end_date | string}})
            AND source_uuid = CAST({{source_uuid | string}} as uuid)
        group by vm_name
    ) vm
        ON strpos(pod_labels, vm.substring) != 0
    WHERE storage.persistentvolumeclaim IS NOT NULL
        AND storage.persistentvolumeclaim != ''
        AND pod_usage.year = {{year}}
        AND pod_usage.month = {{month}}
        AND pod_usage.source = {{source_uuid | string}}
        AND pod_usage.pod_labels != ''
        AND pod_usage.pod_labels IS NOT NULL
    GROUP BY storage.persistentvolumeclaim, vm_name
)
SELECT CAST(map_agg(pvc.persistentvolumeclaim, pvc.vm_name) as json) AS combined_json
FROM cte_mappings pvc
