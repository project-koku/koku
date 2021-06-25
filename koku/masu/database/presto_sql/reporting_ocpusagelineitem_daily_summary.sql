/*
 * Process OCP Usage Data Processing SQL
 * This SQL will utilize Presto for the raw line-item data aggregating
 * and store the results into the koku database summary tables.
 */
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
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
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    infrastructure_usage_cost
)
-- node label line items by day presto sql
WITH cte_ocp_node_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.node,
        nli.node_labels
    FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items_daily AS nli
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= TIMESTAMP {{start_date}}
       AND nli.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
    GROUP BY date(nli.interval_start),
        nli.node,
        nli.node_labels
),
-- namespace label line items by day presto sql
cte_ocp_namespace_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.namespace,
        nli.namespace_labels
    FROM hive.{{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily AS nli
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= TIMESTAMP {{start_date}}
       AND nli.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
    GROUP BY date(nli.interval_start),
        nli.namespace,
        nli.namespace_labels
),
-- Daily sum of cluster CPU and memory capacity
cte_ocp_cluster_capacity AS (
    SELECT date(cc.interval_start) as usage_start,
        sum(cc.max_cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(cc.max_cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM (
        SELECT li.interval_start,
            li.node,
            max(li.node_capacity_cpu_core_seconds) as max_cluster_capacity_cpu_core_seconds,
            max(li.node_capacity_memory_byte_seconds) as max_cluster_capacity_memory_byte_seconds
        FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS li
        WHERE li.source = {{source}}
            AND li.year = {{year}}
            AND li.month = {{month}}
            AND li.interval_start >= TIMESTAMP {{start_date}}
            AND li.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
        GROUP BY li.interval_start,
            li.node
    ) as cc
    GROUP BY date(cc.interval_start)
),
-- Determine which node a PVC is running on
cte_volume_nodes AS (
    SELECT date(sli.interval_start) as usage_start,
        sli.persistentvolumeclaim,
        max(uli.node) as node,
        max(uli.resource_id) as resource_id
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as sli
    JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as uli
        ON uli.source = sli.source
            AND uli.namespace = sli.namespace
            AND uli.pod = sli.pod
            AND date(uli.interval_start) = date(sli.interval_start)
     WHERE sli.source = {{source}}
        AND sli.year = {{year}}
        AND sli.month = {{month}}
        AND sli.interval_start >= TIMESTAMP {{start_date}}
        AND sli.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
        AND uli.source = {{source}}
        AND uli.year = {{year}}
        AND uli.month = {{month}}
     GROUP BY date(sli.interval_start),
          sli.persistentvolumeclaim
)
/*
 * ====================================
 *            POD
 * ====================================
 */
SELECT uuid() as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Pod' as data_source,
    pua.usage_start,
    pua.usage_start as usage_end,
    pua.namespace,
    pua.node,
    pua.resource_id,
    cast(pua.pod_labels as json) as pod_labels,
    pua.pod_usage_cpu_core_hours,
    pua.pod_request_cpu_core_hours,
    pua.pod_limit_cpu_core_hours,
    pua.pod_usage_memory_gigabyte_hours,
    pua.pod_request_memory_gigabyte_hours,
    pua.pod_limit_memory_gigabyte_hours,
    pua.node_capacity_cpu_cores,
    pua.node_capacity_cpu_core_hours,
    pua.node_capacity_memory_gigabytes,
    pua.node_capacity_memory_gigabyte_hours,
    pua.cluster_capacity_cpu_core_hours,
    pua.cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    cast(pua.source_uuid as UUID) as source_uuid,
    JSON '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost
FROM (
    SELECT date(li.interval_start) as usage_start,
        li.namespace,
        li.node,
        li.source as source_uuid,
        map_concat(
            cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
            cast(json_parse(coalesce(nsli.namespace_labels, '{}')) as map(varchar, varchar)),
            cast(json_parse(li.pod_labels) as map(varchar, varchar))
        ) as pod_labels,
        max(li.resource_id) as resource_id,
        sum(li.pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours,
        sum(li.pod_request_cpu_core_seconds) / 3600.0  as pod_request_cpu_core_hours,
        sum(li.pod_limit_cpu_core_seconds) / 3600.0 as pod_limit_cpu_core_hours,
        sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_usage_memory_gigabyte_hours,
        sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_request_memory_gigabyte_hours,
        sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_limit_memory_gigabyte_hours,
        max(li.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        sum(li.node_capacity_cpu_core_seconds) / 3600.0 as node_capacity_cpu_core_hours,
        max(li.node_capacity_memory_bytes) * power(2, -30) as node_capacity_memory_gigabytes,
        sum(li.node_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as node_capacity_memory_gigabyte_hours,
        max(cc.cluster_capacity_cpu_core_seconds) / 3600.0 as cluster_capacity_cpu_core_hours,
        max(cc.cluster_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as cluster_capacity_memory_gigabyte_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as li
    LEFT JOIN cte_ocp_node_label_line_item_daily as nli
        ON nli.node = li.node
            AND nli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
        ON nsli.namespace = li.namespace
            AND nsli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_cluster_capacity as cc
        ON cc.usage_start = date(li.interval_start)
    WHERE li.source = {{source}}
        AND li.year = {{year}}
        AND li.month = {{month}}
        AND li.interval_start >= TIMESTAMP {{start_date}}
        AND li.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
    GROUP BY date(li.interval_start),
        li.namespace,
        li.node,
        li.source,
        5  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE map_filter EXPRESSION */
            /* The map_filter expression was too complex for presto to use */
) as pua

UNION

/*
 * ====================================
 *            STORAGE
 * ====================================
 */
SELECT uuid() as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Storage' as data_source,
    sua.usage_start,
    sua.usage_start as usage_end,
    sua.namespace,
    sua.node,
    sua.resource_id,
    NULL as pod_labels,
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    NULL as node_capacity_cpu_cores,
    NULL as node_capacity_cpu_core_hours,
    NULL as node_capacity_memory_gigabytes,
    NULL as node_capacity_memory_gigabyte_hours,
    NULL as cluster_capacity_cpu_core_hours,
    NULL as cluster_capacity_memory_gigabyte_hours,
    sua.persistentvolumeclaim,
    sua.persistentvolume,
    sua.storageclass,
    cast(sua.volume_labels as json) as volume_labels,
    (sua.persistentvolumeclaim_capacity_bytes *
          power(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
    (sua.persistentvolumeclaim_capacity_byte_seconds /
          (86400 *
          cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
          power(2, -30))) as persistentvolumeclaim_capacity_gigabyte_months,
    (sua.volume_request_storage_byte_seconds /
          (86400 *
          cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
          power(2, -30))) as volume_request_storage_gigabyte_months,
    (sua.persistentvolumeclaim_usage_byte_seconds /
          (86400 *
          cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
          power(2, -30))) as persistentvolumeclaim_usage_gigabyte_months,
    cast(sua.source_uuid as UUID) as source_uuid,
    JSON '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost
FROM (
    SELECT sli.namespace,
        vn.node,
        vn.resource_id,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.storageclass,
        date(sli.interval_start) as usage_start,
        map_concat(
            cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
            cast(json_parse(coalesce(nsli.namespace_labels, '{}')) as map(varchar, varchar)),
            cast(json_parse(sli.persistentvolume_labels) as map(varchar, varchar)),
            cast(json_parse(sli.persistentvolumeclaim_labels) as map(varchar, varchar))
        ) as volume_labels,
        sli.source as source_uuid,
        max(sli.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
        sum(sli.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
        sum(sli.volume_request_storage_byte_seconds) as volume_request_storage_byte_seconds,
        sum(sli.persistentvolumeclaim_usage_byte_seconds) as persistentvolumeclaim_usage_byte_seconds
      FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily sli
      LEFT JOIN cte_volume_nodes as vn
          ON vn.usage_start = date(sli.interval_start)
              AND vn.persistentvolumeclaim = sli.persistentvolumeclaim
      LEFT JOIN cte_ocp_node_label_line_item_daily as nli
          ON nli.node = vn.node
            AND nli.usage_start = vn.usage_start
      LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
          ON nsli.namespace = sli.namespace
              AND nsli.usage_start = date(sli.interval_start)
    WHERE sli.source = {{source}}
        AND sli.year = {{year}}
        AND sli.month = {{month}}
        AND sli.interval_start >= TIMESTAMP {{start_date}}
        AND sli.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
    GROUP BY sli.namespace,
        vn.node,
        vn.resource_id,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.storageclass,
        date(sli.interval_start),
        8,  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE map_filter EXPRESSION */
            /* The map_filter expression was too complex for presto to use */
        sli.source
) as sua
;
