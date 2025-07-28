SELECT
    sum(cost_model_cpu_cost) as cpu_cost,
    sum(cost_model_memory_cost) as memory_cost,
    sum(cost_model_volume_cost) as volume_cost,
    monthly_cost_type,
    namespace,
    node,
    usage_start,
    pod_labels
FROM reporting_ocpusagelineitem_daily_summary
WHERE cost_model_rate_type = 'Infrastructure'
GROUP BY
    monthly_cost_type,
    namespace,
    node,
    usage_start,
    pod_labels
ORDER BY
    pod_labels,
    namespace,
    node,
    usage_start,
    monthly_cost_type;
