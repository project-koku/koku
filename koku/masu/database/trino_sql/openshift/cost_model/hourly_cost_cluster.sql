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

WITH cte_cluster_usage_hours AS (
    SELECT
        CAST(source AS VARCHAR) AS source,
        DATE(interval_start) AS interval_day,
        COUNT(DISTINCT interval_start) AS cluster_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE source = {{source_uuid}} AND
          YEAR(cast(interval_start as date)) = YEAR(cast({{start_date}} as date)) AND
          MONTH(cast(interval_start as date)) = MONTH(cast({{start_date}} as date))
    GROUP BY source, DATE(interval_start)
)

SELECT uuid(),
    max(report_period_id) AS report_period_id,
    lids.cluster_id,
    lids.cluster_alias,
    data_source,
    lids.usage_start,
    max(usage_end) AS usage_end,
    lids.namespace,
    node,
    max(resource_id) AS resource_id,
    pod_labels,
    all_labels,
    source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    (max(clusterhrs.cluster_hours) * CAST({{cluster_cost_per_hour}} AS DECIMAL(33, 15))) AS cost_model_cpu_cost,
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_cluster_usage_hours AS clusterhrs
    ON CAST(lids.source_uuid AS VARCHAR) = clusterhrs.source
    AND clusterhrs.interval_day = lids.usage_start
WHERE lids.usage_start BETWEEN DATE({{start_date}}) AND DATE({{end_date}})
    AND report_period_id = {{report_period_id}}
    AND data_source = 'Pod'
    AND lids.monthly_cost_type IS NULL
    AND pod_usage_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours IS NOT NULL
    AND pod_request_cpu_core_hours != 0
GROUP BY lids.usage_start,
         usage_end,
         source_uuid,
         lids.cluster_id,
         lids.cluster_alias,
         node,
         lids.namespace,
         data_source,
         cost_category_id,
         pod_labels,
         all_labels
 LIMIT 1
;
