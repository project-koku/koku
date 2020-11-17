/*
 * Process OCP Usage Data Processing SQL
 * This SQL will utilize Presto for the raw line-item data aggregating
 * and store the results into the koku database summary tables.
 */

-- Using the convention of a double-underscore prefix to denote a temp table.

/*
 * ====================================
 *    Gather label key, value info
 * ====================================
 */

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}} (
    interval_start timestamp,
    namespace varchar,
    node varchar,
    label_key varchar,
    label_value varchar
)
;


/*
 * Gather pod labels with node labels
 */
INSERT INTO hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}} (
    interval_start,
    namespace,
    node,
    label_key,
    label_value
)
SELECT pl.interval_start,
       pl.namespace,
       pl.node,
       pl.label_key,
       pl.label_value
  FROM (
           SELECT u.interval_start,
                  u.namespace,
                  u.node,
                  l.label_key,
                  l.label_value
             FROM (
                      SELECT opu.interval_start,
                             opu.namespace,
                             opu.node,
                             opu.pod_labels as "labels"
                        FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items opu
                       WHERE opu.source = {{source}}
                         AND opu.year = {{year}}
                         AND opu.month = {{month}}
                         AND opu.interval_start >= TIMESTAMP {{start_date}}
                         AND opu.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
                       UNION
                      SELECT nl.interval_start,
                             opu1.namespace,
                             nl.node,
                             nl.node_labels as "labels"
                        FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items nl
                        JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items opu1
                          ON opu1.interval_start = nl.interval_start
                         AND opu1.node = nl.node
                       WHERE nl.source = {{source}}
                         AND nl.year = {{year}}
                         AND nl.month = {{month}}
                         AND nl.interval_start >= TIMESTAMP {{start_date}}
                         AND nl.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
                         AND nl.node_labels != '{}'
                  ) as "u",
                  unnest(cast(json_parse(u.labels) as map(varchar, varchar))) as l(label_key, label_value)
       ) as "pl"
;

/*
 * Gather volume and volume claim labels with node labels
 */
INSERT INTO hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}} (
    interval_start,
    namespace,
    node,
    label_key,
    label_value
)
SELECT vl.interval_start,
       vl.namespace,
       vl.node,
       vl.label_key,
       vl.label_value
  FROM (
           SELECT u.interval_start,
                  u.namespace,
                  u.node,
                  l.label_key,
                  l.label_value
             FROM (
                      SELECT ops.interval_start,
                             ops.namespace,
                             opu.node,
                             ops.persistentvolume_labels as "labels"
                        FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items ops
                        JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items opu
                          ON opu.interval_start = ops.interval_start
                         AND opu.namespace = ops.namespace
                         AND opu.pod = ops.pod
                       WHERE ops.source = {{source}}
                         AND ops.year = {{year}}
                         AND ops.month = {{month}}
                         AND ops.interval_start >= TIMESTAMP {{start_date}}
                         AND ops.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
                       UNION
                      SELECT opsc.interval_start,
                             opsc.namespace,
                             opu.node,
                             opsc.persistentvolumeclaim_labels as "labels"
                        FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items opsc
                        JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items opu
                          ON opu.interval_start = opsc.interval_start
                         AND opu.namespace = opsc.namespace
                         AND opu.pod = opsc.pod
                       WHERE opsc.source = {{source}}
                         AND opsc.year = {{year}}
                         AND opsc.month = {{month}}
                         AND opsc.interval_start >= TIMESTAMP {{start_date}}
                         AND opsc.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
                       UNION
                      SELECT nl.interval_start,
                             ops1.namespace,
                             nl.node,
                             nl.node_labels as "labels"
                        FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items nl
                        JOIN hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items opu1
                          ON opu1.interval_start = nl.interval_start
                         AND opu1.node = nl.node
                        JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items ops1
                          ON ops1.interval_start = opu1.interval_start
                         AND ops1.pod = opu1.pod
                       WHERE nl.source = {{source}}
                         AND nl.year = {{year}}
                         AND nl.month = {{month}}
                         AND nl.interval_start >= TIMESTAMP {{start_date}}
                         AND nl.interval_start < date_add('day', 1, TIMESTAMP {{end_date}})
                         AND nl.node_labels != '{}'
                  ) as "u",
                  unnest(cast(json_parse(u.labels) as map(varchar, varchar))) as l(label_key, label_value)
       ) as "vl"
;

/*
 * De-duplicate the gathered values
 */
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}};
CREATE TABLE hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}} (
    report_period_id integer,
    cluster_id varchar,
    cluster_alias varchar,
    namespace varchar,
    node varchar,
    label_key varchar,
    label_value varchar
)
;

INSERT INTO hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}} (
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
    label_key,
    label_value
)
SELECT DISTINCT
       prp.id as "report_period_id",
       prp.cluster_id,
       prp.cluster_alias,
       lsg.namespace,
       lsg.node,
       lsg.label_key,
       lsg.label_value
  FROM hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}} lsg
  JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagereportperiod prp
    ON prp.id in {{report_period_ids | inclause}}
   AND lsg.interval_start >= prp.report_period_start
   AND lsg.interval_start <= prp.report_period_end
;

-- DROP gather table as it is no longer needed
DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__label_summary_gather_{{uuid | sqlsafe}};


/*
 * ====================================
 *   Update the reporting_reporting_ocpusagepodlabel_summary data
 * ====================================
 */

/*
 * Store primary key values for any overlapping data for
 * (report_period_id, namespace, node, label_key)
 * for use in the delete log wrapper
 */
INSERT INTO postgres.{{schema | sqlsafe}}.presto_pk_delete_wrapper_log (
    transaction_id,
    action_ts,
    table_name,
    pk_column,
    pk_value,
    pk_value_cast
)
SELECT DISTINCT
       {{uuid}},
       const_time.action_ts,
       'reporting_ocpusagepodlabel_summary',
       'uuid',
       cast(pls.uuid as varchar),
       'uuid'
  FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary pls
  JOIN hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}} ls
    ON ls.report_period_id = pls.report_period_id
   AND ls.namespace = pls.namespace
   AND ls.node = pls.node
   AND ls.label_key = pls.key
 CROSS
  JOIN (
           SELECT now() as action_ts
       ) as const_time;

/*
 * Delete any conflicting entries as we cannot do update processing from presto
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
    'reporting_ocpusagepodlabel_summary',
    'using {{schema | sqlsafe}}.presto_pk_delete_wrapper_log ' ||
    'where presto_pk_delete_wrapper_log.transaction_id = '{{uuid}}' ' ||
      'and presto_pk_delete_wrapper_log.table_name = ''reporting_ocpusagepodlabel_summary'' ' ||
      'and reporting_ocpusagepodlabel_summary."uuid" = presto_pk_delete_wrapper_log.pk_value::uuid ; ',
    null
)
;

/*
 * Insert new/updated records
 */
INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpusagepodlabel_summary (
    "uuid",
    report_period_id,
    namespace,
    node,
    key,
    "values"
)
SELECT uuid() as "uuid",
       als.report_period_id,
       als.namespace,
       als.node,
       als.key,
       als."values"
  FROM (
           SELECT report_period_id,
                  namespace,
                  node,
                  label_key as "key",
                  array_agg(label_value) as "values"
             FROM hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}}
            GROUP
               BY report_period_id,
                  namespace,
                  node,
                  label_key
       ) as "als"
;

/*
 * Delete the queued primary key deletes
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
    'presto_pk_delete_wrapper_log',
    'where transaction_id = '{{uuid}}' ' ||
      'and table_name = ''reporting_ocpusagepodlabel_summary'' ;',
    null
)
;


/*
 * ====================================
 *   Update the reporting_ocptags_values data
 * ====================================
 */

/*
 * Store primary key values for any overlapping data for
 * (key, value)
 * for use in the delete log wrapper
 */
INSERT INTO postgres.{{schema | sqlsafe}}.presto_pk_delete_wrapper_log (
    transaction_id,
    action_ts,
    table_name,
    pk_column,
    pk_value,
    pk_value_cast
)
SELECT DISTINCT
       {{uuid}},
       const_time.action_ts,
       'reporting_ocptags_values',
       'uuid',
       cast(tv.uuid as varchar),
       'uuid'
  FROM postgres.{{schema | sqlsafe}}.reporting_ocptags_values tv
  JOIN hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}} ls
    ON ls.label_key = tv.key
   AND ls.label_value = tv.value
 CROSS
  JOIN (
           SELECT now() as action_ts
       ) as const_time;

/*
 * Delete any conflicting entries as we cannot do update processing from presto
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
    'reporting_ocptags_values',
    'using {{schema | sqlsafe}}.presto_pk_delete_wrapper_log ' ||
    'where presto_pk_delete_wrapper_log.transaction_id = '{{uuid}}' ' ||
      'and presto_pk_delete_wrapper_log.table_name = ''reporting_ocptags_values'' ' ||
      'and reporting_ocptags_values."uuid" = presto_pk_delete_wrapper_log.pk_value::uuid ; ',
    null
)
;

/*
 * Insert the new/updated records
 */
INSERT
  INTO postgres.{{schema | sqlsafe}}.reporting_ocptags_values (
       "uuid",
       key,
       value,
       cluster_ids,
       cluster_aliases,
       namespaces,
       nodes
   )
SELECT uuid() as "uuid",
       lsa.key,
       lsa.value,
       lsa.cluster_ids,
       lsa.cluster_aliases,
       lsa.namespaces,
       lsa.nodes
  FROM (
           SELECT label_key as "key",
                  label_value as "value",
                  array_agg(distinct cluster_id) as "cluster_ids",
                  array_agg(distinct cluster_alias) as "cluster_aliases",
                  array_agg(distinct namespace) as "namespaces",
                  array_agg(distinct node) as "nodes"
             FROM hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}}
            GROUP
               BY label_key,
                  label_value
       ) lsa
;

/*
 * Delete the queued primary key deletes
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
    'presto_pk_delete_wrapper_log',
    'where transaction_id = '{{uuid}}' ' ||
      'and table_name = ''reporting_ocptags_values'' ;',
    null
)
;


/*
 * ====================================
 *               CLEANUP
 * ====================================
 */

DROP TABLE IF EXISTS hive.{{schema | sqlsafe}}.__label_summary_{{uuid | sqlsafe}};
