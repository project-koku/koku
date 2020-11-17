/*
 * Process OCP Usage Data Processing SQL
 * This SQL will utilize Presto for the raw line-item data aggregating
 * and store the results into the koku database summary tables.
 */

-- Using the convention of a double-underscore prefix to denote a temp table.

/*
 * ====================================
 *               COMMON
 * ====================================
 */

-- node label line items by day presto sql
-- still using a "temp" table here because there is no guarantee how big this might get
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}} AS (
    SELECT {{cluster_id}} as "cluster_id",
           date(nli.interval_start) as "usage_start",
           max(nli.node) as "node",
           nli.node_labels,
           max(nli.source) as "source",
           max(nli.year) as "year",
           max(nli.month) as "month"
      FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items as "nli"
     WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= TIMESTAMP {{start_date}}
       AND nli.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
     GROUP
        BY {{cluster_id}},
           date(nli.interval_start),
           nli.node_labels
)
;

/*
 * ====================================
 *                POD
 * ====================================
 */

-- cluster daily cappacity presto sql
-- still using a "temp" table here because there is no guarantee how big this might get
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}} as (
    SELECT {{cluster_id}} as "cluster_id",
           usage_start,
           max(cc.source) as "source",
           max(cc.year) as "year",
           max(cc.month) as "month",
           sum(cc.max_cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
           sum(cc.max_cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
      FROM (
               SELECT date(li.interval_start) as usage_start,
                      max(li.source) as "source",
                      max(li.year) as "year",
                      max(li.month) as "month",
                      max(li.node_capacity_cpu_core_seconds) as "max_cluster_capacity_cpu_core_seconds",
                      max(li.node_capacity_memory_byte_seconds) as "max_cluster_capacity_memory_byte_seconds"
                 FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items AS li
                WHERE li.source = {{source}}
                  AND li.year = {{year}}
                  AND li.month = {{month}}
                  AND date(li.interval_start) >= DATE {{start_date}}
                  AND date(li.interval_start) <= DATE {{end_date}}
                GROUP
                   BY date(li.interval_start)
           ) as cc
     GROUP
        BY {{cluster_id}},
           usage_start
)
;

/*
 * Delete the old block of data (if any) based on the usage range
 * Inserting a record in this log will trigger a delete against the specified table
 * in the same schema as the log table with the specified where_clause
 * start_date and end_date MUST be strings in order for this to work properly.
 */
INSERT
  INTO postgres.{{schema | sqlsafe}}.presto_delete_wrapper_log
       (
           id,
           action_ts,
           table_name,
           where_clause,
           result_rows
       )
VALUES (
    uuid(),
    now(),
    'reporting_ocpusagelineitem_daily_summary',
    'where usage_start >= '{{start_date}}'::date ' ||
      'and usage_start <= '{{end_date}}'::date ' ||
      'and cluster_id = '{{cluster_id}}' ' ||
      'and data_source = ''Pod''',
    null
)
;

/*
 * This is the target summarization sql for POD usage
 * It combines the prior daily summarization query with the final summarization query
 * by use of MAP_FILTER to filter the combined node line item labels as well as
 * the line-item pod labels against the postgres enabled keys in the same query
 */
INSERT
  INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_presto
       (
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
           source_uuid,
           infrastructure_usage_cost
       )
SELECT uuid() as "uuid",
       {{report_period_id}} as "report_period_id",
       {{cluster_id}} as "cluster_id",
       {{cluster_alias}} as "cluster_alias",
       'Pod' as "data_source",
       pua.usage_start,
       pua.usage_start as "usage_end",
       pua.namespace,
       pua.node,
       pua.resource_id,
       cast(pua.pod_labels as json) as "pod_labels",
       cast(pua.pod_usage_cpu_core_hours as varchar) as "pod_usage_cpu_core_hours",
       cast(pua.pod_request_cpu_core_hours as varchar) as "pod_request_cpu_core_hours",
       cast(pua.pod_limit_cpu_core_hours as varchar) as "pod_limit_cpu_core_hours",
       cast(pua.pod_usage_memory_gigabyte_hours as varchar) as "pod_usage_memory_gigabyte_hours",
       cast(pua.pod_request_memory_gigabyte_hours as varchar) as "pod_request_memory_gigabyte_hours",
       cast(pua.pod_limit_memory_gigabyte_hours as varchar) as "pod_limit_memory_gigabyte_hours",
       cast(pua.node_capacity_cpu_cores as varchar) as "node_capacity_cpu_cores",
       cast(pua.node_capacity_cpu_core_hours as varchar) as "node_capacity_cpu_core_hours",
       cast(pua.node_capacity_memory_gigabytes as varchar) as "node_capacity_memory_gigabytes",
       cast(pua.node_capacity_memory_gigabyte_hours as varchar) as "node_capacity_memory_gigabyte_hours",
       cast(pua.cluster_capacity_cpu_core_hours as varchar) as "cluster_capacity_cpu_core_hours",
       cast(pua.cluster_capacity_memory_gigabyte_hours as varchar) as "cluster_capacity_memory_gigabyte_hours",
       cast(pua.source_uuid as UUID) as "source_uuid",
       JSON '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as "infrastructure_usage_cost"
  FROM (
           SELECT date(li.interval_start) as "usage_start",
                  li.namespace,
                  li.node,
                  li.source as "source_uuid",
                  map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                        cast(json_parse(li.pod_labels) as map(varchar, varchar))),
                             (k, v) -> contains(ek.enabled_keys, k)) as "pod_labels",
                  max(li.resource_id) as "resource_id",
                  sum(li.pod_usage_cpu_core_seconds) / 3600.0 as "pod_usage_cpu_core_hours",
                  sum(li.pod_request_cpu_core_seconds) / 3600.0  as "pod_request_cpu_core_hours",
                  sum(li.pod_limit_cpu_core_seconds) / 3600.0 as "pod_limit_cpu_core_hours",
                  sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_usage_memory_gigabyte_hours",
                  sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_request_memory_gigabyte_hours",
                  sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_limit_memory_gigabyte_hours",
                  max(li.node_capacity_cpu_cores) as "node_capacity_cpu_cores",
                  sum(li.node_capacity_cpu_core_seconds) / 3600.0 as "node_capacity_cpu_core_hours",
                  max(li.node_capacity_memory_bytes) * power(2, -30) as "node_capacity_memory_gigabytes",
                  sum(li.node_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as "node_capacity_memory_gigabyte_hours",
                  max(cc.cluster_capacity_cpu_core_seconds) / 3600.0 as "cluster_capacity_cpu_core_hours",
                  max(cc.cluster_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as "cluster_capacity_memory_gigabyte_hours"
             FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items as "li"
             LEFT
             JOIN hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}} as "nli"
               ON nli.node = li.node
              AND nli.usage_start = date(li.interval_start)
              AND nli.source = li.source
             LEFT
             JOIN hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}} as "cc"
               ON cc.source = li.source
              AND cc.usage_start = date(li.interval_start)
            CROSS
             JOIN (
                      SELECT array_agg(distinct key) as "enabled_keys"
                        FROM postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys
                  ) as "ek"
            WHERE li.source = {{source}}
              AND li.year = {{year}}
              AND li.month = {{month}}
              AND date(li.interval_start) >= DATE {{start_date}}
              AND date(li.interval_start) <= DATE {{end_date}}
            GROUP
               BY date(li.interval_start),
                  li.namespace,
                  li.node,
                  li.source,
                  5
                  /*
                  map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                        cast(json_parse(li.pod_labels) as map(varchar, varchar))),
                             (k, v) -> contains(ek.enabled_keys, k))
                   */
       ) as "pua"
;


/*
 * ====================================
 *            STORAGE
 * ====================================
 */

-- Storage node label line items
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__volume_nodes_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__volume_nodes_{{uuid | sqlsafe}} as (
    SELECT sli.namespace,
           sli.pod,
           date(sli.interval_start) as "usage_start",
           max(uli.node) as "node",
           sli.source,
           sli.year,
           sli.month
      FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items as "sli"
      JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items as "uli"
        ON uli.source = sli.source
       AND uli.year = sli.year
       AND uli.month = sli.month
       AND uli.namespace = sli.namespace
       AND uli.pod = sli.pod
       AND date(uli.interval_start) = date(sli.interval_start)
     WHERE sli.source = {{source}}
       AND sli.year = {{year}}
       AND sli.month = {{month}}
       AND date(sli.interval_start) >= DATE {{start_date}}
       AND date(sli.interval_start) <= DATE {{end_date}}
     GROUP
        BY sli.namespace,
           sli.pod,
           date(sli.interval_start),
           sli.source,
           sli.year,
           sli.month
)
;

/*
 * Delete the old block of data (if any) based on the usage range
 * Inserting a record in this log will trigger a delete against the specified table
 * in the same schema as the log table with the specified where_clause
 * start_date and end_date MUST be strings in order for this to work properly.
 */
INSERT
  INTO postgres.{{schema | sqlsafe}}.presto_delete_wrapper_log
       (
           id,
           action_ts,
           table_name,
           where_clause,
           result_rows
       )
VALUES (
    uuid(),
    now(),
    'reporting_ocpusagelineitem_daily_summary',
    'where usage_start >= '{{start_date}}'::date ' ||
      'and usage_start <= '{{end_date}}'::date ' ||
      'and cluster_id = '{{cluster_id}}' ' ||
      'and data_source = ''Storage''',
    null
)
;

/*
 * This is the target summarization sql for STORAGE usage
 * It combines the prior daily summarization query with the final summarization query
 * by use of MAP_FILTER to filter the combined node line item labels as well as
 * the line-item pod labels against the postgres enabled keys in the same query
 */
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_presto (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    usage_start,
    usage_end,
    volume_labels,
    source_uuid,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months
)
SELECT uuid() as "uuid",
       {{report_period_id}} as "report_period_id",
       {{cluster_id}} as "cluster_id",
       {{cluster_alias}} as "cluster_alias",
       'Storage' as "data_source",
       sua.namespace,
       sua.node,
       sua.persistentvolumeclaim,
       sua.persistentvolume,
       sua.storageclass,
       sua.usage_start,
       sua.usage_start as "usage_end",
       cast(sua.volume_labels as json) as "volume_labels",
       cast(sua.source_uuid as UUID) as "source_uuid",
       cast((sua.persistentvolumeclaim_capacity_bytes *
             power(2, -30)) as varchar) as "persistentvolumeclaim_capacity_gigibytes",
       cast((sua.persistentvolumeclaim_capacity_byte_seconds /
             86400 *
             cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
             power(2, -30)) as varchar) as "persistentvolumeclaim_capacity_gigabyte_months",
       cast((sua.volume_request_storage_byte_seconds /
             86400 *
             cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
             power(2, -30)) as varchar) as "volume_request_storage_gigabyte_months",
       cast((sua.persistentvolumeclaim_usage_byte_seconds /
             86400 *
             cast(extract(day from last_day_of_month(date(sua.usage_start))) as integer) *
             power(2, -30)) as varchar) as "persistentvolumeclaim_usage_byte_months"
  FROM (
           SELECT sli.namespace,
                  vn.node,
                  sli.persistentvolumeclaim,
                  sli.persistentvolume,
                  sli.storageclass,
                  date(sli.interval_start) as "usage_start",
                  map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                        cast(json_parse(sli.persistentvolume_labels) as map(varchar, varchar)),
                                        cast(json_parse(sli.persistentvolumeclaim_labels) as map(varchar, varchar))),
                             (k, v) -> contains(ek.enabled_keys, k)) as "volume_labels",
                  sli.source as "source_uuid",
                  max(sli.persistentvolumeclaim_capacity_bytes) as "persistentvolumeclaim_capacity_bytes",
                  sum(sli.persistentvolumeclaim_capacity_byte_seconds) as "persistentvolumeclaim_capacity_byte_seconds",
                  sum(sli.volume_request_storage_byte_seconds) as "volume_request_storage_byte_seconds",
                  sum(sli.persistentvolumeclaim_usage_byte_seconds) as "persistentvolumeclaim_usage_byte_seconds"
             FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items "sli"
             LEFT
             JOIN hive.{{schema | sqlsafe}}.__volume_nodes_{{uuid | sqlsafe}} as "vn"
               ON vn.source = sli.source
              AND vn.year = sli.year
              AND vn.month = sli.month
              AND vn.namespace = sli.namespace
              AND vn.pod = sli.pod
              AND vn.usage_start = date(sli.interval_start)
             LEFT
             JOIN hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}} as "nli"
               ON nli.source = vn.source
              AND nli.year = vn.year
              AND nli.month = vn.month
              AND nli.node = vn.node
              AND date(nli.usage_start) = date(vn.usage_start)
            CROSS
             JOIN (
                    SELECT array_agg(distinct key) as enabled_keys
                      FROM postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys
                  ) as "ek"
            WHERE sli.source = {{source}}
              AND sli.year = {{year}}
              AND sli.month = {{month}}
              AND date(sli.interval_start) >= DATE {{start_date}}
              AND date(sli.interval_start) <= DATE {{end_date}}
            GROUP
               BY sli.namespace,
                  vn.node,
                  sli.persistentvolumeclaim,
                  sli.persistentvolume,
                  sli.storageclass,
                  date(sli.interval_start),
                  7,
                  /*
                  map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                        cast(json_parse(sli.persistentvolume_labels) as map(varchar, varchar)),
                                        cast(json_parse(sli.persistentvolumeclaim_labels) as map(varchar, varchar))),
                             (k, v) -> contains(ek.enabled_keys, k)),
                   */
                  sli.source
       ) as "sua"
;


/*
 * ====================================
 *               CLEANUP
 * ====================================
 */

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}};
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}};
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__volume_nodes_{{uuid | sqlsafe}};
