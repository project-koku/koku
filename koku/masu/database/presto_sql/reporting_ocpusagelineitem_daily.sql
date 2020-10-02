
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
     WHERE nli.source = UUID {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND date(nli.interval_start) >= DATE {{start_date}}
       AND date(nli.interval_start) <= DATE {{end_date}}
     GROUP
        BY 1, 2, 4
)
;

-- cluster daily cappacity presto sql
-- still using a "temp" table here because there is no guarantee how big this might get
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}} as (
    SELECT {{cluster_id}} as "cluster_id",
           date(cc.interval_start) as usage_start,
           max(cc.source) as "source",
           max(cc.year) as "year",
           max(cc.month) as "month",
           sum(cc.max_cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
           sum(cc.max_cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
      FROM (
               SELECT li.interval_start,
                      max(li.source) as "source",
                      max(li.year) as "year",
                      max(li.month) as "month",
                      max(li.node_capacity_cpu_core_seconds) as "max_cluster_capacity_cpu_core_seconds",
                      max(li.node_capacity_memory_byte_seconds) as "max_cluster_capacity_memory_byte_seconds"
                 FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items AS li
                WHERE li.source = UUID {{source}}
                  AND li.year = {{year}}
                  AND li.month = {{month}}
                  AND date(li.interval_start) >= DATE {{start_date}}
                  AND date(li.interval_start) <= DATE {{end_date}}
                GROUP
                   BY 1, 2
           ) as cc
     GROUP
        BY 1, 2
)
;


-- Delete the old block of data (if any) based on the usage range
DELETE
  FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
 WHERE usage_start >= {{start_date}}
   AND usage_start <= {{end_date}}
   AND cluster_id = {{cluster_id}}
   AND data_source = 'Pod'
;

-- This is the target summarization sql
-- It combines the prior daily summarization query with the final summarization query
-- by use of MAP_FILTER to filter the combined node line item labels as well as
-- the line-item pod labels against the postgres enabled keys in the same query
INSERT
  INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
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
           pod_usage_memory_byte_hours,
           pod_request_memory_byte_hours,
           pod_limit_memory_byte_hours,
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
       date(li.interval_start) as "usage_start",
       date(li.interval_start) as "usage_end",
       li.namespace,
       li.node,
       max(li.resource_id) as "resource_id",
       map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                             cast(json_parse(li.pod_labels) as map(varchar, varchar))),
                  (k, v) -> contains(ek.enabled_keys, k)) as "pod_labels",
       sum(li.pod_usage_cpu_core_seconds) / 3600.0 as "pod_usage_cpu_core_hours",
       sum(li.pod_request_cpu_core_seconds) / 3600.0  as "pod_request_cpu_core_hours",
       sum(li.pod_limit_cpu_core_seconds) / 3600.0 as "pod_limit_cpu_core_hours",
       sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_usage_memory_byte_hours",
       sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_request_memory_byte_hours",
       sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as "pod_limit_memory_byte_hours",
       max(li.node_capacity_cpu_cores) as "node_capacity_cpu_cores",
       sum(li.node_capacity_cpu_core_seconds) / 3600.0 as "node_capacity_cpu_core_hours",
       max(li.node_capacity_memory_bytes) * power(2, -30) as "node_capacity_memory_gigabytes",
       sum(li.node_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as "node_capacity_memory_gigabyte_hours",
       max(cc.cluster_capacity_cpu_core_seconds) / 3600.0 as "cluster_capacity_cpu_core_hours",
       max(cc.cluster_capacity_memory_byte_seconds) / 3600.0 * power(2, -30) as "cluster_capacity_memory_gigabyte_hours",
       li.source as "source_uuid",
       '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost
  FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items as "li"
  LEFT
  JOIN hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{schema | sqlsafe}} as "nli"
    ON nli.node = li.node
   AND nli.usage_start = date(li.interval_start)
   AND nli.source = li.source
  LEFT
  JOIN hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{schema | sqlsafe}} as "cc"
    ON cc.source = li.source
   AND cc.usage_start = date(li.interval_start)
 CROSS
  JOIN (
         SELECT array_agg(distinct key) as "enabled_keys"
           FROM postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys
       ) as "ek"
 WHERE li.source = UUID {{source}}
   AND li.year = {{year}}
   AND li.month = {{month}}
   AND date(li.interval_start) >= DATE {{start_date}}
   AND date(li.interval_start) <= DATE {{end_date}}
 GROUP
    BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 24, 25
)
;

-- Drop temps
DROP TABLE hive.{{schema | sqlsafe}}.__ocp_node_label_line_item_daily_{{schema | sqlsafe}};
DROP TABLE hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{schema | sqlsafe}};
