
-- ============================================================================================
-- NOTE TO ANY PREVIEWERS:: I'm using "uuid_eek" as a placeholder so I don't forget to change
--                          that back to jinja templating (along with the hardcoded values)
--                          for use in the app.
-- ============================================================================================

-- Using the convention of a double-underscore prefix to denote a temp table.

-- node label line items by day presto sql
-- still using a "temp" table here because there is no guarantee how big this might get
DROP TABLE IF EXISTS hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek;
CREATE TABLE hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek AS (
    SELECT cast(p_src.authentication as MAP(varchar, MAP(varchar, varchar)))['credentials']['cluster_id'] as "cluster_id",
           date(nli.interval_start) as "usage_start",
           max(nli.node) as "node",
           nli.node_labels,
           count(nli.interval_start) * 3600 as "total_seconds",
           max(nli.source) as "source",
           max(nli.year) as "year",
           max(nli.month) as "month"
      FROM hive.acct10001.openshift_node_labels_line_items as "nli"
      JOIN postgres.public.api_sources p_src
        ON cast(p_src.source_uuid as varchar) = nli.source
     WHERE nli.source = '511aab54-5b4f-4c69-a985-325ff9aa1329'
       AND nli.year = '2020'
       AND nli.month = '09'
       AND date(nli.interval_start) >= DATE '2020-09-01'
       AND date(nli.interval_start) <= DATE '2020-09-08'
     GROUP
        BY 1, 2, 4
)
;

-- cluster daily cappacity presto sql
-- still using a "temp" table here because there is no guarantee how big this might get
DROP TABLE IF EXISTS hive.acct10001.__ocp_cluster_capacity_uuid_eek;
CREATE TABLE hive.acct10001.__ocp_cluster_capacity_uuid_eek as (
    SELECT cc.cluster_id,
           coalesce(cc.cluster_alias, cc.cluster_id) as "cluster_alias",
           date(cc.interval_start) as usage_start,
           max(cc.source) as "source",
           max(cc.year) as "year",
           max(cc.month) as "month",
           sum(cc.max_cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
           sum(cc.max_cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
      FROM (
               SELECT cast(p_src.authentication as MAP(varchar, MAP(varchar, varchar)))['credentials']['cluster_id'] as "cluster_id",
                      p_src.name as "cluster_alias",
                      li.interval_start,
                      max(li.source) as "source",
                      max(li.year) as "year",
                      max(li.month) as "month",
                      max(li.node_capacity_cpu_core_seconds) as "max_cluster_capacity_cpu_core_seconds",
                      max(li.node_capacity_memory_byte_seconds) as "max_cluster_capacity_memory_byte_seconds"
                 FROM hive.acct10001.openshift_pod_usage_line_items AS li
                 JOIN postgres.public.api_sources p_src
                   ON cast(p_src.source_uuid as varchar) = li.source
                WHERE li.source = '511aab54-5b4f-4c69-a985-325ff9aa1329'
                  AND li.year = '2020'
                  AND li.month = '09'
                  AND date(li.interval_start) >= DATE '2020-09-01'
                  AND date(li.interval_start) <= DATE '2020-09-08'
                GROUP
                   BY 1, 2, 3
           ) as cc
     GROUP
        BY 1, 2, 3
)
;

-- This is the target summarization sql
-- It combines the prior daily summarization query with the final summarization query
-- by use of MAP_FILTER to filter the combined node line item labels as well as
-- the line-item pod labels against the postgres enabled keys in the same query
DROP TABLE IF EXISTS hive.acct10001.__reporting_ocpusagelineitem_daily_uuid_eek;
CREATE TABLE hive.acct10001.__reporting_ocpusagelineitem_daily_uuid_eek AS (
    SELECT li.report_period_start,
           cc.cluster_id,
           cc.cluster_alias,
           date(li.interval_start) as "usage_start",
           date(li.interval_start) as "usage_end",
           li.namespace,
           li.pod,
           li.node,
           max(li.resource_id) as "resource_id",
           map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                 cast(json_parse(li.pod_labels) as map(varchar, varchar))),
                      (k, v) -> contains(ek.enabled_keys, k)) as "pod_labels",
           sum(li.pod_usage_cpu_core_seconds) as "pod_usage_cpu_core_seconds",
           sum(li.pod_request_cpu_core_seconds) as "pod_request_cpu_core_seconds",
           sum(li.pod_limit_cpu_core_seconds) as "pod_limit_cpu_core_seconds",
           sum(li.pod_usage_memory_byte_seconds) as "pod_usage_memory_byte_seconds",
           sum(li.pod_request_memory_byte_seconds) as "pod_request_memory_byte_seconds",
           sum(li.pod_limit_memory_byte_seconds) as "pod_limit_memory_byte_seconds",
           max(li.node_capacity_cpu_cores) as "node_capacity_cpu_cores",
           sum(li.node_capacity_cpu_core_seconds) as "node_capacity_cpu_core_seconds",
           max(li.node_capacity_memory_bytes) as "node_capacity_memory_bytes",
           sum(li.node_capacity_memory_byte_seconds) as "node_capacity_memory_byte_seconds",
           max(cc.cluster_capacity_cpu_core_seconds) as "cluster_capacity_cpu_core_seconds",
           max(cc.cluster_capacity_memory_byte_seconds) as "cluster_capacity_memory_byte_seconds",
           count(li.interval_start) * 3600 as "total_seconds"
      FROM hive.acct10001.openshift_pod_usage_line_items as "li"
      LEFT
      JOIN hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek as "nli"
        ON nli.node = li.node
       AND nli.usage_start = date(li.interval_start)
       AND nli.source = li.source
      LEFT
      JOIN hive.acct10001.__ocp_cluster_capacity_uuid_eek as "cc"
        ON cc.source = li.source
       AND cc.usage_start = date(li.interval_start)
     CROSS
      JOIN (
               SELECT array_agg(distinct key) as enabled_keys
                 FROM postgres.acct10001.reporting_ocpenabledtagkeys
           ) as "ek"
     WHERE li.source = '511aab54-5b4f-4c69-a985-325ff9aa1329'
       AND li.year = '2020'
       AND li.month = '09'
       AND date(li.interval_start) >= DATE '2020-09-01'
       AND date(li.interval_start) <= DATE '2020-09-08'
     GROUP
        BY 1, 2, 3, 4, 5, 6, 7, 8, 10
)
;

-- Drop temps
DROP TABLE hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek;
DROP TABLE hive.acct10001.__ocp_cluster_capacity_uuid_eek;


/*
-- Calculate cluster capacity at daily level
CREATE TABLE hive.{{schema | sqlsafe}}.__ocp_cluster_capacity_{{uuid | sqlsafe}} AS (
    SELECT cc.cluster_id,
        date(cc.interval_start) as usage_start,
        sum(cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM (
        SELECT rp.cluster_id,
            ur.interval_start,
            max(li.node_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
            max(li.node_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
        FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem AS li
        JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        WHERE date(ur.interval_start) >= {{start_date}}
            AND date(ur.interval_start) <= {{end_date}}
        GROUP BY rp.cluster_id,
            ur.interval_start,
            li.node
        ) AS cc
        GROUP BY cc.cluster_id,
            date(cc.interval_start)
);
*/

/*
-- Place our query in a temporary table
CREATE TABLE hive.acct10001.__reporting_ocpusagelineitem_daily_uuid_eek AS (
    SELECT  li.report_period_id,
        rp.cluster_id,
        coalesce(max(p.name), rp.cluster_id) as cluster_alias,
        date(ur.interval_start) as usage_start,
        date(ur.interval_start) as usage_end,
        li.namespace,
        li.pod,
        li.node,
        max(li.resource_id) as resource_id,
        COALESCE(nli.node_labels, '{}'::jsonb) || li.pod_labels AS pod_labels,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_core_seconds) as pod_limit_cpu_core_seconds,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_byte_seconds) as pod_limit_memory_byte_seconds,
        max(li.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        sum(li.node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
        max(li.node_capacity_memory_bytes) as node_capacity_memory_bytes,
        sum(li.node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds,
        max(cc.cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        max(cc.cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds,
        count(ur.interval_start) * 3600 as total_seconds
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem AS li
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereport AS ur
        ON li.report_id = ur.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    JOIN ocp_cluster_capacity_{{uuid | sqlsafe}} AS cc
        ON rp.cluster_id = cc.cluster_id
            AND date(ur.interval_start) = cc.usage_start
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpnodelabellineitem AS nli
            ON li.report_id = nli.report_id
                AND li.node = nli.node
    LEFT JOIN public.api_provider AS p
        ON rp.provider_id = p.uuid
    WHERE date(ur.interval_start) >= {{start_date}}
        AND date(ur.interval_start) <= {{end_date}}
        AND rp.cluster_id = {{cluster_id}}
    GROUP BY li.report_period_id,
        rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.node,
        COALESCE(nli.node_labels, '{}'::jsonb) || li.pod_labels
)
;

*/

/*
-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily (
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    pod,
    node,
    resource_id,
    pod_labels,
    pod_usage_cpu_core_seconds,
    pod_request_cpu_core_seconds,
    pod_limit_cpu_core_seconds,
    pod_usage_memory_byte_seconds,
    pod_request_memory_byte_seconds,
    pod_limit_memory_byte_seconds,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_seconds,
    node_capacity_memory_bytes,
    node_capacity_memory_byte_seconds,
    cluster_capacity_cpu_core_seconds,
    cluster_capacity_memory_byte_seconds,
    total_seconds
)
    SELECT report_period_id,
        cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        namespace,
        pod,
        node,
        resource_id,
        pod_labels,
        pod_usage_cpu_core_seconds,
        pod_request_cpu_core_seconds,
        pod_limit_cpu_core_seconds,
        pod_usage_memory_byte_seconds,
        pod_request_memory_byte_seconds,
        pod_limit_memory_byte_seconds,
        node_capacity_cpu_cores,
        node_capacity_cpu_core_seconds,
        node_capacity_memory_bytes,
        node_capacity_memory_byte_seconds,
        cluster_capacity_cpu_core_seconds,
        cluster_capacity_memory_byte_seconds,
        total_seconds
    FROM reporting_ocpusagelineitem_daily_{{uuid | sqlsafe}}
;

-- no need to wait on commit
TRUNCATE TABLE reporting_ocpusagelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpusagelineitem_daily_{{uuid | sqlsafe}};
*/
