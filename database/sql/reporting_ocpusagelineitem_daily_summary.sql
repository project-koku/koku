-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_summary_{uuid} AS (
    SELECT  li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        li.usage_start,
        li.usage_end,
        labels.key as pod_label_key,
        labels.value as pod_label_value,
        li.pod_usage_cpu_core_seconds / 3600 as pod_usage_cpu_core_hours,
        li.pod_request_cpu_core_seconds / 3600 as pod_request_cpu_core_hours,
        li.pod_limit_cpu_core_seconds / 3600 as pod_limit_cpu_core_hours,
        li.pod_usage_memory_byte_seconds / 3600 * 1e-9 as pod_usage_memory_gigabyte_hours,
        li.pod_request_memory_byte_seconds / 3600 * 1e-9 as pod_request_memory_gigabyte_hours,
        li.pod_limit_memory_byte_seconds / 3600 * 1e-9 as pod_limit_memory_gigabyte_hours,
        li.node_capacity_cpu_cores,
        li.node_capacity_cpu_core_seconds / 3600 as node_capacity_cpu_core_hours,
        li.node_capacity_memory_bytes * 1e-9 as node_capacity_memory_gigabytes,
        li.node_capacity_memory_byte_seconds / 3600 * 1e-9 as node_capacity_memory_gigabyte_hours,
        li.cluster_capacity_cpu_core_seconds / 3600 as cluster_capacity_cpu_core_hours,
        li.cluster_capacity_memory_byte_seconds / 3600 * 1e-9 as cluster_capacity_memory_gigabyte_hours
    FROM reporting_ocpusagelineitem_daily AS li,
        jsonb_each_text(li.pod_labels) labels
    WHERE usage_start >= '{start_date}'
        AND usage_start <= '{end_date}'
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
    pod_label_key,
    pod_label_value,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours
)
    SELECT cluster_id,
        namespace,
        pod,
        node,
        usage_start,
        usage_end,
        pod_label_key,
        pod_label_value,
        pod_usage_cpu_core_hours,
        pod_request_cpu_core_hours,
        pod_limit_cpu_core_hours,
        pod_usage_memory_gigabyte_hours,
        pod_request_memory_gigabyte_hours,
        pod_limit_memory_gigabyte_hours,
        node_capacity_cpu_cores,
        node_capacity_cpu_core_hours,
        node_capacity_memory_gigabytes,
        node_capacity_memory_gigabyte_hours,
        cluster_capacity_cpu_core_hours,
        cluster_capacity_memory_gigabyte_hours
    FROM reporting_ocpusagelineitem_daily_summary_{uuid}
;
