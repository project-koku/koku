DROP TABLE IF EXISTS hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek;
CREATE TABLE hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek AS (
    SELECT cast(p_src.authentication as MAP(varchar, MAP(varchar, varchar)))['credentials']['cluster_id'] as "cluster_id",
           p_src.name as "cluster_alias",
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
        BY 1, 2, 3, 5
)
;


DROP TABLE IF EXISTS hive.acct10001.__volume_nodes_uuid_eek;
CREATE TABLE hive.acct10001.__volume_nodes_uuid_eek as (
    SELECT sli.namespace,
           sli.pod,
           date(sli.interval_start) as "usage_start",
           max(uli.node) as "node",
           sli.source,
           sli.year,
           sli.month
      FROM hive.acct10001.openshift_storage_usage_line_items as "sli"
      JOIN hive.acct10001.openshift_pod_usage_line_items as "uli"
        ON uli.source = sli.source
       AND uli.year = sli.year
       AND uli.month = sli.month
       AND uli.namespace = sli.namespace
       AND uli.pod = sli.pod
       AND date(uli.interval_start) = date(sli.interval_start)
     WHERE sli.source = '511aab54-5b4f-4c69-a985-325ff9aa1329'
       AND sli.year = '2020'
       AND sli.month = '09'
       AND date(sli.interval_start) >= DATE '2020-09-01'
       AND date(sli.interval_start) <= DATE '2020-09-08'
     GROUP
        BY 1, 2, 3, 4, 5, 7, 8, 9
)
;


DROP TABLE IF EXISTS hive.acct10001.__reporting_ocpstoragelineitem_daily_uuid_eek;
CREATE TABLE hive.acct10001.__reporting_ocpstoragelineitem_daily_uuid_eek AS (
    SELECT nli.cluster_id,
           coalesce(nli.cluster_alias, vn.cluster_id) as "cluster_alias",
           date(sli.interval_start) as "usage_start",
           date(sli.interval_start) as "usage_end",
           sli.namespace,
           sli.pod,
           vn.node,
           sli.persistentvolumeclaim,
           sli.persistentvolume,
           sli.storageclass,
           sli.persistentvolume_labels,
           map_filter(map_concat(cast(json_parse(coalesce(nli.node_labels, '{}')) as map(varchar, varchar)),
                                 cast(json_parse(sli.persistentvolumeclaim_labels) as map(varchar, varchar))),
                      (k, v) -> contains(ek.enabled_keys, k)) as "pod_labels",
           sum(sli.persistentvolumeclaim_capacity_byte_seconds) as "persistentvolumeclaim_capacity_byte_seconds",
           sum(sli.volume_request_storage_byte_seconds) as "volume_request_storage_byte_seconds",
           sum(sli.persistentvolumeclaim_usage_byte_seconds) as "persistentvolumeclaim_usage_byte_seconds",
           max(sli.persistentvolumeclaim_capacity_bytes) as "persistentvolumeclaim_capacity_bytes",
           count(sli.interval_start) * 3600 as "total_seconds"
      FROM hive.acct10001.openshift_storage_usage_line_items "sli"
      LEFT
      JOIN hive.acct10001.__volume_nodes_uuid_eek as "vn"
        ON vn.source = sli.source
       AND vn.year = sli.year
       AND vn.month = sli.month
       AND vn.namespace = sli.namespace
       AND vn.pod = sli.pod
       AND vn.usage_start = date(sli.interval_start)
      LEFT
      JOIN hive.acct10001.__ocp_node_label_line_item_daily_uuid_eek as "nli"
        ON nli.source = vn.source
       AND nli.year = vn.year
       AND nli.month = vn.month
       AND nli.node = vn.node
       AND date(nli.usage_start) = date(vn.usage_start)
     CROSS
      JOIN (
               SELECT array_agg(distinct key) as enabled_keys
                 FROM postgres.acct10001.reporting_ocpenabledtagkeys
           ) as "ek"
     WHERE sli.source = '511aab54-5b4f-4c69-a985-325ff9aa1329'
       AND sli.year = '2020'
       AND sli.month = '09'
       AND date(sli.interval_start) >= DATE '2020-09-01'
       AND date(sli.interval_start) <= DATE '2020-09-08'
     GROUP
        BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
)
;


/*
CREATE TEMPORARY TABLE volume_nodes_{{uuid | sqlsafe}} AS (
    SELECT li.id,
        uli.node
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem as li
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as uli
        ON li.pod = uli.pod
            AND li.namespace = uli.namespace
            AND rp.cluster_id = uli.cluster_id
    GROUP BY li.id, uli.node
)
;
*/

/*
CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        rp.cluster_id,
        coalesce(max(p.name), rp.cluster_id) as cluster_alias,
        date(ur.interval_start) as usage_start,
        date(ur.interval_start) as usage_end,
        li.namespace,
        li.pod,
        max(uli.node) as node,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels,
        COALESCE(nli.node_labels, '{}'::jsonb) || li.persistentvolumeclaim_labels AS persistentvolumeclaim_labels,
        sum(li.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
        sum(li.volume_request_storage_byte_seconds) as volume_request_storage_byte_seconds,
        sum(li.persistentvolumeclaim_usage_byte_seconds) as persistentvolumeclaim_usage_byte_seconds,
        max(li.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
        count(ur.interval_start) * 3600 as total_seconds
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem AS li
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereport AS ur
        ON li.report_id = ur.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    LEFT JOIN public.api_provider as p
        ON rp.provider_id = p.uuid
    LEFT JOIN volume_nodes_{{uuid | sqlsafe}} as uli
        ON li.id = uli.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpnodelabellineitem AS nli
            ON li.report_id = nli.report_id
                AND uli.node = nli.node
    WHERE date(ur.interval_start) >= {{start_date}}
        AND date(ur.interval_start) <= {{end_date}}
        AND rp.cluster_id = {{cluster_id}}
    GROUP BY li.report_period_id,
        rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels,
        COALESCE(nli.node_labels, '{}'::jsonb) || li.persistentvolumeclaim_labels
)
;

-- no need to wait on commit
TRUNCATE TABLE volume_nodes_{{uuid | sqlsafe}};
DROP TABLE volume_nodes_{{uuid | sqlsafe}};


-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily (
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    pod,
    node,
    persistentvolume_labels,
    persistentvolumeclaim_labels,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    persistentvolumeclaim_capacity_bytes,
    persistentvolumeclaim_capacity_byte_seconds,
    volume_request_storage_byte_seconds,
    persistentvolumeclaim_usage_byte_seconds,
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
        persistentvolume_labels,
        persistentvolumeclaim_labels,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        persistentvolumeclaim_capacity_bytes,
        persistentvolumeclaim_capacity_byte_seconds,
        volume_request_storage_byte_seconds,
        persistentvolumeclaim_usage_byte_seconds,
        total_seconds
    FROM reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}}
;

-- no need to wait for commit
TRUNCATE TABLE reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}};
*/
