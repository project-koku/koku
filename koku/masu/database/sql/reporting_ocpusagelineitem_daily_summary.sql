-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_summary_{uuid} AS (
    SELECT  li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.resource_id,
        li.usage_start,
        li.usage_end,
        li.pod_labels,
        li.pod_usage_cpu_core_seconds / 3600 as pod_usage_cpu_core_hours,
        li.pod_request_cpu_core_seconds / 3600 as pod_request_cpu_core_hours,
        li.pod_limit_cpu_core_seconds / 3600 as pod_limit_cpu_core_hours,
        li.pod_usage_memory_byte_seconds / 3600 * POWER(2, -30) as pod_usage_memory_gigabyte_hours,
        li.pod_request_memory_byte_seconds / 3600 * POWER(2, -30) as pod_request_memory_gigabyte_hours,
        li.pod_limit_memory_byte_seconds / 3600 * POWER(2, -30) as pod_limit_memory_gigabyte_hours,
        li.node_capacity_cpu_cores,
        li.node_capacity_cpu_core_seconds / 3600 as node_capacity_cpu_core_hours,
        li.node_capacity_memory_bytes * POWER(2, -30) as node_capacity_memory_gigabytes,
        li.node_capacity_memory_byte_seconds / 3600 * POWER(2, -30) as node_capacity_memory_gigabyte_hours,
        li.cluster_capacity_cpu_core_seconds / 3600 as cluster_capacity_cpu_core_hours,
        li.cluster_capacity_memory_byte_seconds / 3600 * POWER(2, -30) as cluster_capacity_memory_gigabyte_hours,
        li.total_capacity_cpu_core_seconds / 3600 as total_capacity_cpu_core_hours,
        li.total_capacity_memory_byte_seconds / 3600 * POWER(2, -30) as total_capacity_memory_gigabyte_hours
    FROM {schema}.reporting_ocpusagelineitem_daily AS li
    WHERE usage_start >= '{start_date}'
        AND usage_start <= '{end_date}'
        AND cluster_id = '{cluster_id}'
)
;

-- Clear out old entries first
DELETE FROM {schema}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cluster_id = '{cluster_id}'
    AND data_source = 'Pod'
;

-- Populate the daily aggregate line item data
INSERT INTO {schema}.reporting_ocpusagelineitem_daily_summary (
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    pod,
    node,
    resource_id,
    usage_start,
    usage_end,
    pod_labels,
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
    cluster_capacity_memory_gigabyte_hours,
    total_capacity_cpu_core_hours,
    total_capacity_memory_gigabyte_hours
)
    SELECT cluster_id,
        cluster_alias,
        'Pod',
        namespace,
        pod,
        node,
        resource_id,
        usage_start,
        usage_end,
        pod_labels,
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
        cluster_capacity_memory_gigabyte_hours,
        total_capacity_cpu_core_hours,
         total_capacity_memory_gigabyte_hours
    FROM reporting_ocpusagelineitem_daily_summary_{uuid}
;
