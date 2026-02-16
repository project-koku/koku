INSERT INTO {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (
    vm_name,
    node,
    pvc_name,
    cpu_request,
    mem_request
)
WITH cte_second_to_last_day as (
    SELECT day
        FROM (
            SELECT DISTINCT DATE(usage_start) AS day
            FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= DATE({{start_date}})
                AND usage_start <= DATE({{end_date}})
                AND source_uuid::varchar = {{source_uuid | string}}
                AND pod_request_cpu_core_hours IS NOT NULL
            ORDER BY day DESC
            LIMIT 2
        ) AS  latest_days
    ORDER BY day
    LIMIT 1
)
SELECT
    latest.vm_name,
    latest.node_name,
    pvc.pvc_name,
    latest.cpu_request_hours,
    latest.memory_request_hours
FROM (
    SELECT
        pod_labels->>'vm_kubevirt_io_name' AS vm_name,
        pod_request_cpu_core_hours AS cpu_request_hours,
        pod_request_memory_gigabyte_hours AS memory_request_hours,
        node AS node_name,
        usage_start,
        ROW_NUMBER() OVER (
            PARTITION BY pod_labels->>'vm_kubevirt_io_name'
            ORDER BY usage_start DESC
        ) AS rn
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS summary
    INNER JOIN cte_second_to_last_day as stld
        ON summary.usage_start::date = stld.day
    WHERE
        summary.usage_start >= DATE({{start_date}})
        AND summary.usage_start <= DATE({{end_date}})
        AND pod_request_cpu_core_hours IS NOT NULL
        AND pod_labels->>'vm_kubevirt_io_name' IS NOT NULL
) AS latest
LEFT JOIN (
    SELECT
        storage.persistentvolumeclaim AS pvc_name,
        pod_usage.pod_labels::jsonb->>'vm_kubevirt_io_name' AS vm_name
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS pod_usage
    INNER JOIN {{schema | sqlsafe}}.openshift_storage_usage_line_items_daily AS storage
        ON pod_usage.pod = storage.pod
        AND pod_usage.year = storage.year
        AND pod_usage.month = storage.month
        AND pod_usage.source = storage.source
    WHERE storage.persistentvolumeclaim IS NOT NULL
        AND storage.persistentvolumeclaim != ''
        AND storage.year = {{year}}
        AND storage.month = {{month}}
        AND storage.source = {{source_uuid | string}}
        AND pod_usage.year = {{year}}
        AND pod_usage.month = {{month}}
        AND pod_usage.source = {{source_uuid | string}}
        AND pod_usage.pod_labels::jsonb->>'vm_kubevirt_io_name' IS NOT NULL
    GROUP BY storage.persistentvolumeclaim, pod_usage.pod_labels::jsonb->>'vm_kubevirt_io_name'
) AS pvc
    ON pvc.vm_name = latest.vm_name
WHERE latest.rn = 1
RETURNING 1;
