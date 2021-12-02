/*
 * Process OCP Usage Data Processing SQL
 * This SQL will utilize Presto for the raw line-item data aggregating
 * and store the results into the koku database summary tables.
 */
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid varchar,
    report_period_id int,
    cluster_id varchar,
    cluster_alias varchar,
    data_source varchar,
    usage_start date,
    usage_end date,
    namespace varchar,
    node varchar,
    resource_id varchar,
    pod_labels varchar,
    pod_usage_cpu_core_hours double,
    pod_request_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    pod_limit_memory_gigabyte_hours double,
    node_capacity_cpu_cores double,
    node_capacity_cpu_core_hours double,
    node_capacity_memory_gigabytes double,
    node_capacity_memory_gigabyte_hours double,
    cluster_capacity_cpu_core_hours double,
    cluster_capacity_memory_gigabyte_hours double,
    persistentvolumeclaim varchar,
    persistentvolume varchar,
    storageclass varchar,
    volume_labels varchar,
    persistentvolumeclaim_capacity_gigabyte double,
    persistentvolumeclaim_capacity_gigabyte_months double,
    volume_request_storage_gigabyte_months double,
    persistentvolumeclaim_usage_gigabyte_months double,
    source_uuid varchar,
    infrastructure_usage_cost varchar,
    source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month', 'day'])
;


DELETE
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE source = {{source}}
    AND year = {{year}}
    AND month = {{month}}
    AND day IN ({{days}})
;

INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
    infrastructure_usage_cost,
    source,
    year,
    month,
    day
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
cte_ocp_node_capacity AS (
    SELECT date(nc.interval_start) as usage_start,
        nc.node,
        sum(nc.node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
        sum(nc.node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds
    FROM (
        SELECT li.interval_start,
            li.node,
            max(li.node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
            max(li.node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds
        FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily AS li
        WHERE li.source = {{source}}
            AND li.year = {{year}}
            AND li.month = {{month}}
            AND li.interval_start >= TIMESTAMP {{start_date}}
            AND li.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
        GROUP BY li.interval_start,
            li.node
    ) as nc
    GROUP BY date(nc.interval_start),
        nc.node
),
cte_ocp_cluster_capacity AS (
    SELECT nc.usage_start,
        sum(nc.node_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(nc.node_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM cte_ocp_node_capacity AS nc
    GROUP BY nc.usage_start
),
-- Determine which node a PVC is running on
cte_volume_nodes AS (
    SELECT date(sli.interval_start) as usage_start,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.pod,
        uli.node,
        uli.resource_id
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
          sli.persistentvolumeclaim,
          sli.persistentvolume,
          sli.pod,
          uli.node,
          uli.resource_id
),
cte_shared_volume_node_count AS (
    SELECT usage_start,
        persistentvolume,
        count(DISTINCT node) as node_count
    FROM cte_volume_nodes
    GROUP BY usage_start,
        persistentvolume
)
/*
 * ====================================
 *            POD
 * ====================================
 */
SELECT cast(uuid() as varchar) as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Pod' as data_source,
    pua.usage_start,
    pua.usage_start as usage_end,
    pua.namespace,
    pua.node,
    pua.resource_id,
    json_format(cast(pua.pod_labels as json)) as pod_labels,
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
    pua.source_uuid,
    '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost,
    {{source}} as source,
    cast(year(pua.usage_start) as varchar) as year,
    cast(month(pua.usage_start) as varchar) as month,
    cast(day(pua.usage_start) as varchar) as day
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
        max(nc.node_capacity_cpu_core_seconds) / 3600.0 as node_capacity_cpu_core_hours,
        max(li.node_capacity_memory_bytes) * power(2, -30) as node_capacity_memory_gigabytes,
        max(nc.node_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as node_capacity_memory_gigabyte_hours,
        max(cc.cluster_capacity_cpu_core_seconds) / 3600.0 as cluster_capacity_cpu_core_hours,
        max(cc.cluster_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as cluster_capacity_memory_gigabyte_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as li
    LEFT JOIN cte_ocp_node_label_line_item_daily as nli
        ON nli.node = li.node
            AND nli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
        ON nsli.namespace = li.namespace
            AND nsli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_node_capacity as nc
        ON nc.usage_start = date(li.interval_start)
            AND nc.node = li.node
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
SELECT cast(uuid() as varchar) as uuid,
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
    json_format(cast(sua.volume_labels as json)) as volume_labels,
    (sua.persistentvolumeclaim_capacity_bytes *
        power(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
    (sua.persistentvolumeclaim_capacity_byte_seconds /
        (
            86400 *
            cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer)
        ) *
        power(2, -30)) as persistentvolumeclaim_capacity_gigabyte_months,
    (sua.volume_request_storage_byte_seconds /
        (
            86400 *
            cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer)
        ) *
        power(2, -30)) as volume_request_storage_gigabyte_months,
    (sua.persistentvolumeclaim_usage_byte_seconds /
        (
            86400 *
            cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer)
        ) *
        power(2, -30)) as persistentvolumeclaim_usage_gigabyte_months,
    sua.source_uuid,
    '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost,
    {{source}} as source,
    cast(year(sua.usage_start) as varchar) as year,
    cast(month(sua.usage_start) as varchar) as month,
    cast(day(sua.usage_start) as varchar) as day
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
        -- Divide volume usage and requests by the number of nodes that volume is mounted on
        sum(sli.volume_request_storage_byte_seconds) / max(nc.node_count) as volume_request_storage_byte_seconds,
        sum(sli.persistentvolumeclaim_usage_byte_seconds) / max(nc.node_count) as persistentvolumeclaim_usage_byte_seconds
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily sli
    LEFT JOIN cte_volume_nodes as vn
        ON vn.usage_start = date(sli.interval_start)
            AND vn.persistentvolumeclaim = sli.persistentvolumeclaim
            AND vn.pod = sli.pod
    LEFT JOIN cte_shared_volume_node_count as nc
        ON nc.usage_start = date(sli.interval_start)
            AND nc.persistentvolume = sli.persistentvolume
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
SELECT cast(uuid as UUID),
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    json_parse(pod_labels),
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
    json_parse(volume_labels),
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    cast(source_uuid as UUID),
    json_parse(infrastructure_usage_cost)
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.source = {{source}}
    AND lids.year = {{year}}
    AND lids.month = {{month}}
    AND lids.day IN ({{days}})
    -- AND lids.usage_start >= TIMESTAMP {{start_date}}
    -- AND lids.usage_start < date_add('day', 1, TIMESTAMP {{end_date}})
;
