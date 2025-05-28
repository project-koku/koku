{% if openshift_vm_usage_line_items_daily %}
SELECT
    CAST(map_agg(vm_persistentvolumeclaim_name, vm_name) as json) as combined_json
FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items_daily as vm
WHERE vm.source = {{source_uuid | string}}
AND vm.year = {{year}}
AND vm.month = {{month}}
{% else %}
SELECT CAST(map_agg(pvc.persistentvolumeclaim, pvc.vm_name) as json) AS combined_json
FROM (
    SELECT
        storage.persistentvolumeclaim,
        json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name') as vm_name
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS pod_usage
    INNER JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as storage
        ON pod_usage.pod = storage.pod
        AND pod_usage.year = storage.year
        AND pod_usage.month = storage.month
        AND pod_usage.source = storage.source
    WHERE storage.persistentvolumeclaim IS NOT NULL
        AND storage.persistentvolumeclaim != ''
        AND pod_usage.year = {{year}}
        AND pod_usage.month = {{month}}
        AND pod_usage.source = {{source_uuid | string}}
        AND strpos(lower(pod_labels), 'vm_kubevirt_io_name') != 0
    GROUP BY storage.persistentvolumeclaim, 2
) as pvc
{% endif %}
