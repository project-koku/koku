-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        max(li.resource_id) as resource_id,
        li.usage_start,
        li.usage_end,
        li.pod_labels,
        sum(li.pod_usage_cpu_core_seconds) / 3600 as pod_usage_cpu_core_hours,
        sum(li.pod_request_cpu_core_seconds) / 3600 as pod_request_cpu_core_hours,
        sum(li.pod_limit_cpu_core_seconds) / 3600 as pod_limit_cpu_core_hours,
        sum(li.pod_usage_memory_byte_seconds) / 3600 * POWER(2, -30) as pod_usage_memory_gigabyte_hours,
        sum(li.pod_request_memory_byte_seconds) / 3600 * POWER(2, -30) as pod_request_memory_gigabyte_hours,
        sum(li.pod_limit_memory_byte_seconds) / 3600 * POWER(2, -30) as pod_limit_memory_gigabyte_hours,
        max(li.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        sum(li.node_capacity_cpu_core_seconds) / 3600 as node_capacity_cpu_core_hours,
        max(li.node_capacity_memory_bytes) * POWER(2, -30) as node_capacity_memory_gigabytes,
        sum(li.node_capacity_memory_byte_seconds) / 3600 * POWER(2, -30) as node_capacity_memory_gigabyte_hours,
        max(li.cluster_capacity_cpu_core_seconds) / 3600 as cluster_capacity_cpu_core_hours,
        max(li.cluster_capacity_memory_byte_seconds) / 3600 * POWER(2, -30) as cluster_capacity_memory_gigabyte_hours,
        max(li.total_capacity_cpu_core_seconds) / 3600 as total_capacity_cpu_core_hours,
        max(li.total_capacity_memory_byte_seconds) / 3600 * POWER(2, -30) as total_capacity_memory_gigabyte_hours
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily AS li
    WHERE usage_start >= {{start_date}}
        AND usage_start <= {{end_date}}
        AND cluster_id = {{cluster_id}}
    GROUP BY report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.usage_start,
        li.usage_end,
        li.namespace,
        li.node,
        li.pod_labels
)
;

-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
    AND data_source = 'Pod'
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
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
    SELECT report_period_id,
        cluster_id,
        cluster_alias,
        'Pod',
        namespace,
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
    FROM reporting_ocpusagelineitem_daily_summary_{{uuid | sqlsafe}}
;
