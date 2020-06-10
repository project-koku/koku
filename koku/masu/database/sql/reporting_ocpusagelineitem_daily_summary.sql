-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM {{schema | sqlsafe}}.reporting_ocpenabledtagkeys
    ),
    cte_filtered_pod_labels AS (
        SELECT id,
            jsonb_object_agg(key,value) as pod_labels
        FROM (
            SELECT lid.id,
                lid.pod_labels,
                aak.key_array
            FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.usage_start >= {{start_date}}
                AND lid.usage_start <= {{end_date}}
                AND lid.cluster_id = {{cluster_id}}
                AND lid.pod_labels ?| aak.key_array
        ) AS lid,
        jsonb_each_text(lid.pod_labels) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    ),
    cte_agg_pod_usage as (
        SELECT li.report_period_id,
            li.cluster_id,
            li.cluster_alias,
            li.namespace,
            li.node,
            max(li.resource_id) as resource_id,
            li.usage_start,
            li.usage_end,
            coalesce(fpl.pod_labels, '{}'::jsonb) as pod_labels,
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
        LEFT JOIN cte_filtered_pod_labels AS fpl
            ON li.id = fpl.id
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
            fpl.pod_labels
    )
    SELECT public.koku_record_uuid(apu.cluster_id::text, apu.namespace::text, apu.node::text, apu.pod_labels::text)::uuid as id,
        apu.report_period_id,
        apu.cluster_id,
        apu.cluster_alias,
        apu.namespace,
        apu.node,
        apu.resource_id,
        apu.usage_start,
        apu.usage_end,
        apu.pod_labels,
        apu.pod_usage_cpu_core_hours,
        apu.pod_request_cpu_core_hours,
        apu.pod_limit_cpu_core_hours,
        apu.pod_usage_memory_gigabyte_hours,
        apu.pod_request_memory_gigabyte_hours,
        apu.pod_limit_memory_gigabyte_hours,
        apu.node_capacity_cpu_cores,
        apu.node_capacity_cpu_core_hours,
        apu.node_capacity_memory_gigabytes,
        apu.node_capacity_memory_gigabyte_hours,
        apu.cluster_capacity_cpu_core_hours,
        apu.cluster_capacity_memory_gigabyte_hours,
        apu.total_capacity_cpu_core_hours,
        apu.total_capacity_memory_gigabyte_hours
    FROM cte_agg_pod_usage apu
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
    id,
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
    SELECT id,
        report_period_id,
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
