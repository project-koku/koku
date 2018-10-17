-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_{uuid} AS (
    SELECT  rp.cluster_id,
        date(ur.interval_start) as usage_start,
        date(ur.interval_start) as usage_end,
        li.namespace,
        li.pod,
        li.node,
        sum(li.pod_usage_cpu_core_seconds) as pod_usage_cpu_core_seconds,
        sum(li.pod_request_cpu_core_seconds) as pod_request_cpu_core_seconds,
        sum(li.pod_limit_cpu_cores) as pod_limit_cpu_cores,
        sum(li.pod_usage_memory_byte_seconds) as pod_usage_memory_byte_seconds,
        sum(li.pod_request_memory_byte_seconds) as pod_request_memory_byte_seconds,
        sum(li.pod_limit_memory_bytes) as pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem AS li
    JOIN reporting_ocpusagereport AS ur
        ON li.report_id = ur.id
    JOIN reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    WHERE date(ur.interval_start) >= '{start_date}'
        AND date(ur.interval_start) <= '{end_date}'
    GROUP BY rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.node
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpusagelineitem_daily
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpusagelineitem_daily (
    cluster_id,
    usage_start,
    usage_end,
    namespace,
    pod,
    node,
    pod_usage_cpu_core_seconds,
    pod_request_cpu_core_seconds,
    pod_limit_cpu_cores,
    pod_usage_memory_byte_seconds,
    pod_request_memory_byte_seconds,
    pod_limit_memory_bytes
)
    SELECT cluster_id,
        usage_start,
        usage_end,
        namespace,
        pod,
        node,
        pod_usage_cpu_core_seconds,
        pod_request_cpu_core_seconds,
        pod_limit_cpu_cores,
        pod_usage_memory_byte_seconds,
        pod_request_memory_byte_seconds,
        pod_limit_memory_bytes
    FROM reporting_ocpusagelineitem_daily_{uuid}
;
