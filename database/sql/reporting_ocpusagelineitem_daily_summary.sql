-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_summary_{uuid} AS (
    SELECT  li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        li.usage_start,
        li.usage_end,
        li.pod_usage_cpu_core_seconds / 3600 as pod_usage_cpu_core_hours,
        li.pod_request_cpu_core_seconds / 3600 as pod_request_cpu_core_hours,
        li.pod_limit_cpu_cores,
        li.pod_usage_memory_byte_seconds / li.total_seconds * 1e-9 as pod_usage_memory_gigabytes,
        li.pod_request_memory_byte_seconds / li.total_seconds * 1e-9 as pod_request_memory_gigabytes,
        li.pod_limit_memory_bytes * 1e-9 as pod_limit_memory_gigabytes
    FROM reporting_ocpusagelineitem_daily AS li
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpusagelineitem_daily_summary (
    cluster_id,
    namespace,
    pod,
    node,
    usage_start,
    usage_end,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_cores,
    pod_usage_memory_gigabytes,
    pod_request_memory_gigabytes,
    pod_limit_memory_gigabytes
)
    SELECT cluster_id,
        namespace,
        pod,
        node,
        usage_start,
        usage_end,
        pod_usage_cpu_core_hours,
        pod_request_cpu_core_hours,
        pod_limit_cpu_cores,
        pod_usage_memory_gigabytes,
        pod_request_memory_gigabytes,
        pod_limit_memory_gigabytes
    FROM reporting_ocpusagelineitem_daily_summary_{uuid}
;
