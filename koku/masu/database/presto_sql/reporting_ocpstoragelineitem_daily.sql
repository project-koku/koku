
-- Using the convention of a double-underscore prefix to denote a temp table.

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
       AND date(nli.interval_start) >= DATE {{start_date}}
       AND date(nli.interval_start) <= DATE {{end_date}}
     GROUP
        BY 1, 2, 4
)
;


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
        BY 1, 2, 3, 4, 5, 7, 8, 9
)
;


INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid
)
SELECT {{report_period_id}} as "report_period_id"
       {{cluster_id}} as "cluster_id",
       {{cluster_alias}} as "cluster_alias",
       'Storage' as "data_source",
       sli.namespace,
       vn.node,
       sli.persistentvolumeclaim,
       sli.persistentvolume,
       sli.storageclass,
       date(sli.interval_start) as "usage_start",
       date(sli.interval_start) as "usage_end",
       map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                             cast(json_parse(sli.persistentvolume_labels) as map(varchar, varchar))),
                             cast(json_parse(sli.persistentvolumeclaim_labels) as map(varchar, varchar))),
                  (k, v) -> contains(ek.enabled_keys, k)) as "volume_labels",
       max(sli.persistentvolumeclaim_capacity_bytes) * power(2, -30) as "persistentvolumeclaim_capacity_gigibytes",
       sum(sli.persistentvolumeclaim_capacity_byte_seconds) /
         86400 *
         cast(extract(day from last_day_of_month(date(sli.interval_start))) as integer) *
         power(2, -30) as "persistentvolumeclaim_capacity_gigabyte_months",
       sum(sli.volume_request_storage_byte_seconds) /
         86400 *
         cast(extract(day from last_day_of_month(date(sli.interval_start))) as integer) *
         power(2, -30) as "volume_request_storage_gigabyte_months",
       sum(sli.persistentvolumeclaim_usage_byte_seconds) /
         86400 *
         cast(extract(day from last_day_of_month(date(sli.interval_start))) as integer) *
         power(2, -30) as "persistentvolumeclaim_usage_byte_seconds",
       UUID {{source}} as "source_uuid"
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
    BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 17
)
;

-- drop temps
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{uuid | sqlsafe}};
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__volume_nodes_{{uuid | sqlsafe}};
