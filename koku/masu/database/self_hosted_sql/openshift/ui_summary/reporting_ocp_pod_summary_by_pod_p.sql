DELETE FROM {{schema | sqlsafe}}.reporting_ocp_pod_summary_by_pod_p
WHERE usage_start >= date({{start_date}})
    AND usage_start <= date({{end_date}})
    AND source_uuid = {{source_uuid}}::uuid
;
INSERT INTO {{schema | sqlsafe}}.reporting_ocp_pod_summary_by_pod_p (
    id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    pod,
    usage_start,
    usage_end,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    source_uuid
)
SELECT uuid_generate_v4() as id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    li.namespace,
    li.node,
    li.pod,
    li.usage_start,
    li.usage_start as usage_end,
    sum(li.pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours,
    sum(li.pod_request_cpu_core_seconds) / 3600.0 as pod_request_cpu_core_hours,
    sum(COALESCE(li.pod_effective_usage_cpu_core_seconds, GREATEST(li.pod_usage_cpu_core_seconds, li.pod_request_cpu_core_seconds))) / 3600.0 as pod_effective_usage_cpu_core_hours,
    sum(li.pod_limit_cpu_core_seconds) / 3600.0 as pod_limit_cpu_core_hours,
    sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_usage_memory_gigabyte_hours,
    sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_request_memory_gigabyte_hours,
    sum(COALESCE(li.pod_effective_usage_memory_byte_seconds, GREATEST(li.pod_usage_memory_byte_seconds, li.pod_request_memory_byte_seconds))) / 3600.0 * power(2, -30) as pod_effective_usage_memory_gigabyte_hours,
    sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_limit_memory_gigabyte_hours,
    COALESCE(max(cc.cluster_capacity_cpu_core_seconds), 0) / 3600.0 as cluster_capacity_cpu_core_hours,
    COALESCE(max(cc.cluster_capacity_memory_byte_seconds), 0) / 3600.0 * power(2, -30) as cluster_capacity_memory_gigabyte_hours,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS li
LEFT JOIN (
    SELECT usage_start,
        sum(node_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(node_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM (
        SELECT usage_start, node,
            max(node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
            max(node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds
        FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
        WHERE source = {{source_uuid}}
            AND year = {{year}}
            AND lpad(month, 2, '0') = {{month}}
            AND usage_start >= date({{start_date}})
            AND usage_start <= date({{end_date}})
        GROUP BY usage_start, node
    ) as nc
    GROUP BY usage_start
) as cc ON cc.usage_start = li.usage_start
WHERE li.source = {{source_uuid}}
    AND li.year = {{year}}
    AND lpad(li.month, 2, '0') = {{month}}
    AND li.usage_start >= date({{start_date}})
    AND li.usage_start <= date({{end_date}})
    AND li.node != ''
GROUP BY li.usage_start, li.namespace, li.node, li.pod
RETURNING 1;
