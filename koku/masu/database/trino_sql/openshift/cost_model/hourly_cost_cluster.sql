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
    all_labels,
    source_uuid,
    cost_model_rate_type,
    cost_model_cpu_cost,
    cost_model_memory_cost,
    cost_model_volume_cost,
    cost_category_id
)

-- Get clusters from daily summary
WITH cte_clusters AS (
    SELECT
        DISTINCT cluster_id,
        cluster_alias,
        namespace
    FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS ocp
    WHERE usage_start >= DATE({{start_date}})
        AND usage_start <= DATE({{end_date}})
        AND source_uuid = CAST({{source_uuid}} AS uuid)
        AND pod_request_cpu_core_hours IS NOT NULL
        AND pod_request_cpu_core_hours != 0
),

-- Get number of hours for each cluster
cte_cluster_usage_hours AS (
    SELECT
        cte_clusters.cluster_id AS cluster_id,
        cte_clusters.cluster_alias AS cluster_alias,
        DATE(interval_start) AS interval_day,
        COUNT(DISTINCT EXTRACT(hour FROM pod_usage.interval_start)) AS cluster_interval_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items pod_usage
    INNER JOIN cte_clusters
        ON pod_usage.namespace = cte_clusters.namespace
    WHERE source = {{source_uuid}}
    GROUP BY cte_clusters.cluster_id, cte_clusters.cluster_alias, DATE(interval_start)
)

SELECT uuid(),
    max(report_period_id) AS report_period_id,
    lids.cluster_id,
    max(clusterhrs.cluster_alias) AS cluster_alias,
    'Pod' AS data_source,
    usage_start,
    max(usage_end) AS usage_end,
    NULL AS namespace,
    NULL AS node,
    NULL AS resource_id,
    NULL AS pod_labels,
    NULL AS all_labels,
    source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    max(clusterhrs.cluster_interval_hours) * CAST({{cluster_cost_per_hour}} AS DECIMAL(33, 15)) AS cost_model_cpu_cost,
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    NULL AS cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_cluster_usage_hours AS clusterhrs
    ON lids.cluster_id = clusterhrs.cluster_id
    AND clusterhrs.interval_day = lids.usage_start
WHERE usage_start BETWEEN DATE({{start_date}}) AND DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND lids.monthly_cost_type IS NULL
    AND pod_usage_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
GROUP BY
    lids.cluster_id,
    usage_start,
    source_uuid
;
