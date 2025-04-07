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
        DATE(interval_start) AS interval_day,
        COUNT(DISTINCT interval_start) AS cluster_hours
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items
    WHERE source = {{source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
    GROUP BY DATE(interval_start)
)

SELECT uuid(),
    {{report_period_id}} as report_period_id,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    lids.usage_start,
    max(lids.usage_end) AS usage_end,
    lids.namespace,
    lids.node,
    max(lids.resource_id) AS resource_id,
    lids.pod_labels,
    lids.all_labels,
    lids.source_uuid,
    {{rate_type}} AS cost_model_rate_type,
    (max(clusterhrs.cluster_hours) * CAST({{cluster_cost_per_hour}} AS DECIMAL(33, 15))) AS cost_model_cpu_cost,
    0 AS cost_model_memory_cost,
    0 AS cost_model_volume_cost,
    lids.cost_category_id
FROM postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
JOIN cte_cluster_usage_hours AS clusterhrs
    ON cast({{source_uuid}} as uuid) = lids.source_uuid
    AND clusterhrs.interval_day = lids.usage_start
WHERE lids.usage_start >= date({{start_date}}) AND lids.usage_start <= date({{end_date}})
    AND lids.report_period_id = {{report_period_id}}
    AND lids.data_source = 'Pod'
    AND lids.monthly_cost_type IS NULL
    AND lids.pod_usage_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours IS NOT NULL
    AND lids.pod_request_cpu_core_hours != 0
GROUP BY lids.usage_start,
         lids.usage_end,
         lids.source_uuid,
         lids.cluster_id,
         lids.cluster_alias,
         lids.node,
         lids.namespace,
         lids.data_source,
         lids.cost_category_id,
         lids.pod_labels,
         lids.all_labels
;
