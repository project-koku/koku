DELETE FROM postgres.{{schema | sqlsafe}}.{{temp_table | sqlsafe}}
WHERE 1 = 1;

INSERT INTO postgres.{{schema | sqlsafe}}.{{temp_table | sqlsafe}} (
    vm_name,
    node,
    pvc_name,
    cpu_request,
    mem_request
)
SELECT
    latest.vm_name,
    latest.node_name,
    pvc.pvc_name,
    latest.cpu_request_hours,
    latest.memory_request_hours
FROM (
    SELECT
        json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') AS vm_name,
        pod_request_cpu_core_hours AS cpu_request_hours,
        pod_request_memory_gigabyte_hours AS memory_request_hours,
        node AS node_name,
        usage_start,
        ROW_NUMBER() OVER (
            PARTITION BY json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name')
            ORDER BY usage_start DESC
        ) AS rn
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS summary
    WHERE
        CAST(usage_start AS DATE) = (
            SELECT day
            FROM (
                SELECT DISTINCT DATE(usage_start) AS day
                FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
                WHERE usage_start >= DATE({{start_date}})
                    AND usage_start <= DATE({{end_date}})
                    AND source_uuid = {{source_uuid}}
                    AND pod_request_cpu_core_hours IS NOT NULL
                ORDER BY day DESC
                OFFSET 1 LIMIT 1
            ) AS second_to_last_day
        )
        AND pod_request_cpu_core_hours IS NOT NULL
        AND json_extract_scalar(pod_labels, '$.vm_kubevirt_io_name') IS NOT NULL
) AS latest
INNER JOIN (
    SELECT
        storage.persistentvolumeclaim AS pvc_name,
        json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name') AS vm_name
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS pod_usage
    INNER JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily AS storage
        ON pod_usage.pod = storage.pod
        AND pod_usage.year = storage.year
        AND pod_usage.month = storage.month
        AND pod_usage.source = storage.source
    WHERE storage.persistentvolumeclaim IS NOT NULL
        AND storage.persistentvolumeclaim != ''
        AND pod_usage.year = {{year}}
        AND pod_usage.month = {{month}}
        AND pod_usage.source = {{source_uuid | string}}
        AND json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name') IS NOT NULL
    GROUP BY storage.persistentvolumeclaim, json_extract_scalar(pod_usage.pod_labels, '$.vm_kubevirt_io_name')
) AS pvc
    ON pvc.vm_name = latest.vm_name
WHERE latest.rn = 1;
