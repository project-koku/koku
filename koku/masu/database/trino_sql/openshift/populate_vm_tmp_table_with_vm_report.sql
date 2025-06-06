INSERT INTO postgres.{{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (
    vm_name,
    node,
    pvc_name,
    cpu_request,
    mem_request
)
SELECT
    latest.vm_name,
    latest.node,
    pvc.vm_persistentvolumeclaim_name,
    max(latest.cpu_request),
    max(latest.mem_request)
FROM (
    SELECT
        vm.vm_name,
        vm.node,
        max(vm.vm_cpu_request_cores) as cpu_request,
        max(vm.vm_memory_request_bytes) * power(2, -30) as mem_request
    FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items as vm
    WHERE source = {{source_uuid | string}}
    AND vm.year={{year}}
    AND vm.month={{month}}
    AND vm.interval_start = (
        SELECT MAX(interval_start)
        FROM hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items
        WHERE source = {{source_uuid | string}}
        AND year = {{year}}
        AND month = {{month}}
    )
    GROUP BY vm.vm_name, vm.node
) as latest
INNER JOIN hive.{{schema | sqlsafe}}.openshift_vm_usage_line_items as pvc
ON pvc.vm_name = latest.vm_name
WHERE pvc.source = {{source_uuid | string}}
AND pvc.year = {{year}}
AND pvc.month = {{month}}
GROUP BY latest.vm_name, latest.node, pvc.vm_persistentvolumeclaim_name
