-- RTU demo: per-rate rows (rates_to_usage) -> daily summary cost model cost -> cost breakdown tree.
WITH rtu AS (
    SELECT source_uuid, date_trunc('month', usage_start)::date AS month,
           count(*) AS rtu_rows,
           sum(coalesce(calculated_cost, 0) + coalesce(distributed_cost, 0)) AS rtu_cost
    FROM org7654321.rates_to_usage GROUP BY 1, 2
), ds AS (
    SELECT source_uuid, date_trunc('month', usage_start)::date AS month,
           sum(coalesce(cost_model_cpu_cost, 0) + coalesce(cost_model_memory_cost, 0)
               + coalesce(cost_model_volume_cost, 0) + coalesce(cost_model_gpu_cost, 0)
               + coalesce(distributed_cost, 0)) AS daily_summary_cost
    FROM org7654321.reporting_ocpusagelineitem_daily_summary GROUP BY 1, 2
), bd AS (
    SELECT source_uuid, date_trunc('month', usage_start)::date AS month,
           count(*) AS breakdown_rows,
           sum(coalesce(cost_value, 0) + coalesce(distributed_cost, 0)) FILTER (WHERE path = top_category) AS breakdown_top_cost
    FROM org7654321.reporting_ocp_cost_breakdown_p GROUP BY 1, 2
)
SELECT p.name AS source, rtu.month, rtu.rtu_rows,
       round(rtu.rtu_cost, 2) AS rtu_cost,
       round(ds.daily_summary_cost, 2) AS daily_summary_cost,
       bd.breakdown_rows,
       round(bd.breakdown_top_cost, 2) AS breakdown_top_cost
FROM rtu
JOIN public.api_provider p ON p.uuid = rtu.source_uuid
LEFT JOIN ds ON ds.source_uuid = rtu.source_uuid AND ds.month = rtu.month
LEFT JOIN bd ON bd.source_uuid = rtu.source_uuid AND bd.month = rtu.month
ORDER BY 1, 2;

-- Top-level breakdown categories for cluster A, current month.
SELECT top_category, round(sum(coalesce(cost_value, 0) + coalesce(distributed_cost, 0)), 2) AS cost
FROM org7654321.reporting_ocp_cost_breakdown_p b
JOIN public.api_provider p ON p.uuid = b.source_uuid
WHERE p.name = 'RTU cluster A' AND path = top_category AND usage_start >= date_trunc('month', now())
GROUP BY 1 ORDER BY 2 DESC;
