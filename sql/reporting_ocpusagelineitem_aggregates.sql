-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_aggregates_{uuid} AS (
    SELECT -30 as time_scope_value,
        li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_cores) as pod_limit_cpu_cores,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_bytes) as pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem_daily as li
    WHERE li.usage_start >= current_date - INTERVAL '30 days'
    GROUP BY li.cluster_id, li.namespace, li.pod, li.node

    UNION

    SELECT -10 as time_scope_value,
        li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_cores) as pod_limit_cpu_cores,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_bytes) as pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem_daily as li
    WHERE li.usage_start >= current_date - INTERVAL '10 days'
    GROUP BY li.cluster_id, li.namespace, li.pod, li.node

    UNION

    SELECT -1 as time_scope_value,
        li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_cores) as pod_limit_cpu_cores,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_bytes) as pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem_daily as li
    WHERE li.usage_start >= date_trunc('month', current_date)::date
    GROUP BY li.cluster_id, li.namespace, li.pod, li.node

    UNION

    SELECT -2 as time_scope_value,
        li.cluster_id,
        li.namespace,
        li.pod,
        li.node,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_cores) as pod_limit_cpu_cores,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_bytes) as pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem_daily as li
    WHERE li.usage_start >= (date_trunc('month', current_date) - interval '1 month')
        AND li.usage_start < date_trunc('month', current_date)
    GROUP BY li.cluster_id, li.namespace, li.pod, li.node
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpusagelineitem_aggregates;

-- Populate the aggregate data
INSERT INTO reporting_ocpusagelineitem_aggregates (
    time_scope_value,
    cluster_id,
    namespace,
    pod,
    node,
    pod_usage_cpu_core_seconds,
    pod_request_cpu_core_seconds,
    pod_limit_cpu_cores,
    pod_usage_memory_byte_seconds,
    pod_request_memory_byte_seconds,
    pod_limit_memory_bytes
)
SELECT time_scope_value,
    cluster_id,
    namespace,
    pod,
    node,
    pod_usage_cpu_core_seconds,
    pod_request_cpu_core_seconds,
    pod_limit_cpu_cores,
    pod_usage_memory_byte_seconds,
    pod_request_memory_byte_seconds,
    pod_limit_memory_bytes
FROM reporting_ocpusagelineitem_aggregates_{uuid}
;
