/*
 * Process OCP Usage Data Processing SQL
 * This SQL will utilize Trino for the raw line-item data aggregating
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
    pod_effective_usage_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    pod_effective_usage_memory_gigabyte_hours double,
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
    csi_volume_handle varchar,
    cost_category_id int,
    source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month', 'day'])
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
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
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
    csi_volume_handle,
    cost_category_id,
    source,
    year,
    month,
    day
)
-- node label line items by day trino sql
WITH cte_pg_enabled_keys as (
    select array['vm_kubevirt_io_name'] || array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type = 'OCP'
),
cte_ocp_node_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.node,
        cast(
            map_filter(
                cast(json_parse(nli.node_labels) as map(varchar, varchar)),
                (k,v) -> contains(pek.keys, k)
            ) as json
        ) as node_labels
    FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items_daily AS nli
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= {{start_date}}
       AND nli.interval_start < date_add('day', 1, {{end_date}})
    GROUP BY date(nli.interval_start),
        nli.node,
        3 -- needs to match the lables cardinality
),
-- namespace label line items by day trino sql
cte_ocp_namespace_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.namespace,
        cast(
            map_filter(
                cast(json_parse(nli.namespace_labels) as map(varchar, varchar)),
                (k,v) -> contains(pek.keys, k)
            ) as json
        ) as namespace_labels
    FROM hive.{{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily AS nli
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= {{start_date}}
       AND nli.interval_start < date_add('day', 1, {{end_date}})
    GROUP BY date(nli.interval_start),
        nli.namespace,
        3 -- needs to match the labels cardinality
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
        FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items AS li
        WHERE li.source = {{source}}
            AND li.year = {{year}}
            AND li.month = {{month}}
            AND li.interval_start >= {{start_date}}
            AND li.interval_start < date_add('day', 1, {{end_date}})
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
)
{% if storage_exists %}
,
-- Determine which node a PVC is running on
cte_volume_nodes AS (
    SELECT date(sli.interval_start) as usage_start,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.pod,
        sli.namespace,
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
        AND sli.interval_start >= {{start_date}}
        AND sli.interval_start < date_add('day', 1, {{end_date}})
        AND uli.source = {{source}}
        AND uli.year = {{year}}
        AND uli.month = {{month}}
     GROUP BY date(sli.interval_start),
          sli.persistentvolumeclaim,
          sli.persistentvolume,
          sli.pod,
          sli.namespace,
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
{% endif %}
/*
 * ====================================
 *            POD
 * ====================================
 */
SELECT null as uuid,
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
    pua.pod_effective_usage_cpu_core_hours,
    pua.pod_limit_cpu_core_hours,
    pua.pod_usage_memory_gigabyte_hours,
    pua.pod_request_memory_gigabyte_hours,
    pua.pod_effective_usage_memory_gigabyte_hours,
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
    NULL as csi_volume_handle,
    pua.cost_category_id,
    {{source}} as source,
    cast(year(pua.usage_start) as varchar) as year,
    cast(month(pua.usage_start) as varchar) as month,
    cast(day(pua.usage_start) as varchar) as day
FROM (
    SELECT date(li.interval_start) as usage_start,
        li.namespace,
        li.node,
        max(cat_ns.cost_category_id) as cost_category_id,
        li.source as source_uuid,
        map_concat(
            cast(coalesce(nli.node_labels, cast(map(array[], array[]) as json)) as map(varchar, varchar)),
            cast(coalesce(nsli.namespace_labels, cast(map(array[], array[]) as json)) as map(varchar, varchar)),
            map_filter(
                cast(json_parse(li.pod_labels) AS MAP(VARCHAR, VARCHAR)),
                (k, v) -> CONTAINS(pek.keys, k)
            )
        ) as pod_labels,
        max(li.resource_id) as resource_id,
        sum(li.pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours,
        sum(li.pod_request_cpu_core_seconds) / 3600.0  as pod_request_cpu_core_hours,
        sum(coalesce(li.pod_effective_usage_cpu_core_seconds, greatest(li.pod_usage_cpu_core_seconds, li.pod_request_cpu_core_seconds))) / 3600.0  as pod_effective_usage_cpu_core_hours,
        sum(li.pod_limit_cpu_core_seconds) / 3600.0 as pod_limit_cpu_core_hours,
        sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_usage_memory_gigabyte_hours,
        sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_request_memory_gigabyte_hours,
        sum(coalesce(li.pod_effective_usage_memory_byte_seconds, greatest(pod_usage_memory_byte_seconds, pod_request_memory_byte_seconds))) / 3600.0 * power(2, -30) as pod_effective_usage_memory_gigabyte_hours,
        sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_limit_memory_gigabyte_hours,
        max(li.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(nc.node_capacity_cpu_core_seconds) / 3600.0 as node_capacity_cpu_core_hours,
        max(li.node_capacity_memory_bytes) * power(2, -30) as node_capacity_memory_gigabytes,
        max(nc.node_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as node_capacity_memory_gigabyte_hours,
        max(cc.cluster_capacity_cpu_core_seconds) / 3600.0 as cluster_capacity_cpu_core_hours,
        max(cc.cluster_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as cluster_capacity_memory_gigabyte_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as li
    CROSS JOIN cte_pg_enabled_keys AS pek
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
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON li.namespace LIKE cat_ns.namespace
    WHERE li.source = {{source}}
        AND li.year = {{year}}
        AND li.month = {{month}}
        AND li.interval_start >= {{start_date}}
        AND li.interval_start < date_add('day', 1, {{end_date}})
        AND li.node != ''
    GROUP BY date(li.interval_start),
        li.namespace,
        li.node,
        li.source,
        6  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE map_filter EXPRESSION */
            /* The map_filter expression was too complex for trino to use */
) as pua

{% if storage_exists %}

UNION

/*
 * ====================================
 *            STORAGE
 * ====================================
 */
SELECT null as uuid,
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
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
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
    sua.csi_volume_handle,
    sua.cost_category_id,
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
            cast(coalesce(nli.node_labels, cast(map(array[], array[]) as json)) as map(varchar, varchar)),
            cast(coalesce(nsli.namespace_labels, cast(map(array[], array[]) as json)) as map(varchar, varchar)),
            map_filter(
                cast(json_parse(sli.persistentvolume_labels) AS MAP(VARCHAR, VARCHAR)),
                (k, v) -> CONTAINS(pek.keys, k)
            ),
            map_filter(
                cast(json_parse(sli.persistentvolumeclaim_labels) AS MAP(VARCHAR, VARCHAR)),
                (k, v) -> CONTAINS(pek.keys, k)
            )
        ) as volume_labels,
        sli.source as source_uuid,
        sli.csi_volume_handle as csi_volume_handle,
        max(cat_ns.cost_category_id) as cost_category_id,
        max(sli.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
        sum(sli.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
        -- Divide volume usage and requests by the number of nodes that volume is mounted on
        sum(sli.volume_request_storage_byte_seconds) / max(nc.node_count) as volume_request_storage_byte_seconds,
        sum(sli.persistentvolumeclaim_usage_byte_seconds) / max(nc.node_count) as persistentvolumeclaim_usage_byte_seconds
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily sli
    CROSS JOIN cte_pg_enabled_keys AS pek
    LEFT JOIN cte_volume_nodes as vn
        ON vn.usage_start = date(sli.interval_start)
            AND vn.persistentvolumeclaim = sli.persistentvolumeclaim
            AND vn.pod = sli.pod
            AND vn.namespace = sli.namespace
    LEFT JOIN cte_shared_volume_node_count as nc
        ON nc.usage_start = date(sli.interval_start)
            AND nc.persistentvolume = sli.persistentvolume
    LEFT JOIN cte_ocp_node_label_line_item_daily as nli
        ON nli.node = vn.node
            AND nli.usage_start = vn.usage_start
    LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
        ON nsli.namespace = sli.namespace
            AND nsli.usage_start = date(sli.interval_start)
    LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON sli.namespace LIKE cat_ns.namespace
    WHERE sli.source = {{source}}
        AND sli.year = {{year}}
        AND sli.month = {{month}}
        AND sli.interval_start >= {{start_date}}
        AND sli.interval_start < date_add('day', 1, {{end_date}})
    GROUP BY sli.namespace,
        vn.node,
        vn.resource_id,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.storageclass,
        sli.csi_volume_handle,
        date(sli.interval_start),
        8,  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE map_filter EXPRESSION */
            /* The map_filter expression was too complex for trino to use */
        sli.source
) as sua

{% endif %}

;

/*
 * ====================================
 *        UNALLOCATED CAPACITY
 * ====================================
Developer Note: Add these to make it easier to verify
What was selected from unallocated capacity.
AND lids.namespace != 'Platform unallocated'
AND lids.namespace != 'Worker unallocated'
 */
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    data_source,
    source_uuid,
    cost_category_id,
    source,
    year,
    month,
    day
)
WITH cte_node_role AS (
    SELECT
        max(node_role) AS node_role,
        node,
        resource_id
    FROM postgres.{{schema | sqlsafe}}.reporting_ocp_nodes
    GROUP BY node, resource_id
),
cte_unallocated_capacity AS (
    SELECT
        NULL as uuid,
        {{report_period_id}} as report_period_id,
        {{cluster_id}} as cluster_id,
        {{cluster_alias}} as cluster_alias,
        max(lids.usage_start) as usage_start,
        max(lids.usage_end) as usage_end,
        CASE max(nodes.node_role)
            WHEN 'master' THEN 'Platform unallocated'
            WHEN 'infra' THEN 'Platform unallocated'
            WHEN 'worker' THEN 'Worker unallocated'
        END as namespace,
        lids.node,
        max(lids.resource_id) as resource_id,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_usage_cpu_core_hours)) as pod_usage_cpu_core_hours,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_request_cpu_core_hours)) as pod_request_cpu_core_hours,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_effective_usage_cpu_core_hours)) as pod_effective_usage_cpu_core_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_usage_memory_gigabyte_hours)) as pod_usage_memory_gigabyte_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_request_memory_gigabyte_hours)) as pod_request_memory_gigabyte_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_effective_usage_memory_gigabyte_hours)) as pod_effective_usage_memory_gigabyte_hours,
        max(lids.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(lids.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(lids.node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(lids.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(lids.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(lids.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        max(lids.data_source) as data_source,
        lids.source_uuid,
        {{source}} as source,
        cast(year(lids.usage_start) as varchar) as year,
        cast(month(lids.usage_start) as varchar) as month,
        cast(day(lids.usage_start) as varchar) as day
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as lids
    LEFT JOIN cte_node_role AS nodes
        ON lids.node = nodes.node
        AND lids.resource_id = nodes.resource_id
    WHERE lids.source = {{source}}
        AND lids.year = {{year}}
        AND lpad(lids.month, 2, '0') = {{month}}
        AND lids.usage_start >= {{start_date}}
        AND lids.usage_start < date_add('day', 1, {{end_date}})
        AND lids.namespace != 'Platform unallocated'
        AND lids.namespace != 'Worker unallocated'
        AND lids.namespace != 'Network unattributed'
        AND lids.namespace != 'Storage unattributed'
        AND lids.node IS NOT NULL
        AND lids.data_source = 'Pod'
    GROUP BY lids.node, lids.usage_start, lids.source_uuid
)
SELECT
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    uc.namespace,
    node,
    resource_id,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    data_source,
    source_uuid,
    cat_ns.cost_category_id as cost_category_id,
    source,
    year,
    month,
    day
FROM cte_unallocated_capacity AS uc
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
    ON uc.namespace LIKE cat_ns.namespace
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
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
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
    all_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    cost_category_id
)
SELECT uuid(),
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
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
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
    json_parse(json_format(cast(map_concat(
        cast(json_parse(coalesce(pod_labels, '{}')) as map(varchar, varchar)),
        cast(json_parse(coalesce(volume_labels, '{}')) as map(varchar, varchar))
    )as json))) as all_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    cast(source_uuid as UUID),
    cost_category_id
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.source = {{source}}
    AND lids.year = {{year}}
    AND lpad(lids.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND lids.day IN {{days | inclause}}
;
