-- pod labels extraction
select li.pod_labels,
       map_filter(cast(json_parse(li.pod_labels) as map(varchar, varchar)),
                  (k, v) -> contains(ek.enabled_keys, k)) as "filtered_pod_labels"
  from hive.acct10001.openshift_pod_usage_line_items as li
 cross
  join (
         select array_agg(distinct key) as enabled_keys
           from postgres.acct10001.reporting_ocpenabledtagkeys
       ) as ek
 where li.source = 'cdd92137-0d73-4535-991b-d2d11a190479'
   and li.report_period_start = TIMESTAMP '2020-08-31 20:00:00.000'
 limit 5;

select li.node_labels,
       map_filter(cast(json_parse(li.node_labels) as map(varchar, varchar)),
                  (k, v) -> contains(ek.enabled_keys, k)) as "filtered_node_labels"
  from hive.acct10001.openshift_node_labels_line_items as li
 cross
  join (
         select array_agg(distinct key) as enabled_keys
           from postgres.acct10001.reporting_ocpenabledtagkeys
       ) as ek
 where li.source = 'cdd92137-0d73-4535-991b-d2d11a190479'
   and li.report_period_start = TIMESTAMP '2020-08-31 20:00:00.000'
 limit 5;


select map_filter(cast(json_parse(li.pod_labels) as map(varchar, varchar)),
                  (k, v) -> contains(ek.enabled_keys, k)) as "pod_labels"
  from hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items as li
 cross
  join (
         select array_agg(distinct key) as enabled_keys
           from postgres.{{schema | sqlsafe}}.reporting_ocpenabledtagkeys
       ) as ek
 where li.source = {{source}}
   and li.year = {{start_year}}
   and li.month = {{start_month}}



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

-- no need to wait on commit
TRUNCATE TABLE ocp_cluster_capacity_{{uuid | sqlsafe}};
DROP TABLE ocp_cluster_capacity_{{uuid | sqlsafe}};


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
