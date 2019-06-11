-- Calculate cluster capacity at daily level
CREATE TEMPORARY TABLE ocp_cluster_capacity_{uuid} AS (
    SELECT cc.cluster_id,
        date(cc.interval_start) as usage_start,
        sum(cluster_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(cluster_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM (
        SELECT rp.cluster_id,
            ur.interval_start,
            max(li.node_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
            max(li.node_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
        FROM reporting_ocpusagelineitem AS li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
        GROUP BY rp.cluster_id,
            ur.interval_start,
            li.node
        ) AS cc
        GROUP BY cc.cluster_id,
            date(cc.interval_start)
);

-- Calculate capacity of all clusters combined for a grand total
CREATE TEMPORARY TABLE ocp_capacity_{uuid} AS (
    SELECT cc.usage_start,
        sum(cc.cluster_capacity_cpu_core_seconds) as total_capacity_cpu_core_seconds,
        sum(cc.cluster_capacity_memory_byte_seconds) as total_capacity_memory_byte_seconds
    FROM ocp_cluster_capacity_{uuid} AS cc
    GROUP BY cc.usage_start
);

-- Aggregate pod labels from hourly to daily level
CREATE TEMPORARY TABLE ocp_daily_labels_{uuid} AS (
    SELECT pl.cluster_id,
        pl.namespace,
        pl.pod,
        date(pl.interval_start) as usage_start,
        jsonb_object_agg(key, value) as pod_labels
    FROM (
        SELECT rp.cluster_id,
            li.namespace,
            li.pod,
            ur.interval_start,
            key,
            value
        FROM (
            SELECT report_id,
                report_period_id,
                namespace,
                pod,
                key,
                value
            FROM reporting_ocpusagelineitem AS li,
                jsonb_each_text(li.pod_labels) labels
        ) li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
            AND rp.cluster_id = '{cluster_id}'
        GROUP BY rp.cluster_id,
            li.namespace,
            li.pod,
            key,
            value,
            ur.interval_start
    ) pl
    GROUP BY pl.cluster_id,
        pl.namespace,
        pl.pod,
        date(pl.interval_start)
)
;

-- Place our query in a temporary table
CREATE TEMPORARY TABLE reporting_ocpusagelineitem_daily_{uuid} AS (
    SELECT  rp.cluster_id,
        coalesce(max(p.name), rp.cluster_id) as cluster_alias,
        date(ur.interval_start) as usage_start,
        date(ur.interval_start) as usage_end,
        li.namespace,
        li.pod,
        li.node,
        max(li.resource_id) as resource_id,
        CASE WHEN dl.pod_labels IS NOT NULL
            THEN dl.pod_labels
            ELSE '{{}}'::jsonb
            END as pod_labels,
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
        max(oc.total_capacity_cpu_core_seconds) as total_capacity_cpu_core_seconds,
        max(oc.total_capacity_memory_byte_seconds) as total_capacity_memory_byte_seconds,
        count(ur.interval_start) * 3600 as total_seconds
    FROM reporting_ocpusagelineitem AS li
    JOIN reporting_ocpusagereport AS ur
        ON li.report_id = ur.id
    JOIN reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    JOIN ocp_cluster_capacity_{uuid} AS cc
        ON rp.cluster_id = cc.cluster_id
            AND date(ur.interval_start) = cc.usage_start
    JOIN ocp_capacity_{uuid} AS oc
        ON date(ur.interval_start) = oc.usage_start
    LEFT JOIN ocp_daily_labels_{uuid} AS dl
        ON rp.cluster_id = dl.cluster_id
            AND li.namespace = dl.namespace
            AND li.pod = dl.pod
            AND date(ur.interval_start) = dl.usage_start
    LEFT JOIN public.api_provider AS p
        ON rp.provider_id = p.id
    WHERE date(ur.interval_start) >= '{start_date}'
        AND date(ur.interval_start) <= '{end_date}'
        AND rp.cluster_id = '{cluster_id}'
    GROUP BY rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.node,
        dl.pod_labels
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpusagelineitem_daily
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cluster_id = '{cluster_id}'
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpusagelineitem_daily (
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
    total_capacity_cpu_core_seconds,
    total_capacity_memory_byte_seconds,
    total_seconds
)
    SELECT cluster_id,
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
        total_capacity_cpu_core_seconds,
        total_capacity_memory_byte_seconds,
        total_seconds
    FROM reporting_ocpusagelineitem_daily_{uuid}
;
