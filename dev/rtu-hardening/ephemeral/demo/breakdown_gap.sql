-- Cluster A, October: RTU cost per rate name and type vs the breakdown leaves (depth 3 carry cost_value, depth 4 distributed_cost).
WITH src AS (SELECT uuid FROM public.api_provider WHERE name = 'RTU cluster A'),
rtu AS (
    SELECT coalesce(nullif(custom_name, ''), '(none)') AS custom_name,
           coalesce(cost_model_rate_type, '-') AS rate_type,
           coalesce(monthly_cost_type, '-') AS monthly_cost_type,
           round(sum(coalesce(calculated_cost, 0)), 2) AS rtu_calculated,
           round(sum(coalesce(distributed_cost, 0)), 2) AS rtu_distributed
    FROM org7654321.rates_to_usage
    WHERE source_uuid = (SELECT uuid FROM src) AND usage_start < '2026-11-01'
    GROUP BY 1, 2, 3
), bd AS (
    SELECT custom_name, round(sum(coalesce(cost_value, 0)), 2) AS bd_cost_value,
           round(sum(coalesce(distributed_cost, 0)), 2) AS bd_distributed
    FROM org7654321.reporting_ocp_cost_breakdown_p
    WHERE source_uuid = (SELECT uuid FROM src) AND usage_start < '2026-11-01'
      AND array_length(string_to_array(path, '.'), 1) IN (3, 4)
      AND NOT EXISTS (SELECT 1 FROM org7654321.reporting_ocp_cost_breakdown_p c
                      WHERE c.parent_path = reporting_ocp_cost_breakdown_p.path
                        AND c.source_uuid = reporting_ocp_cost_breakdown_p.source_uuid
                        AND c.usage_start = reporting_ocp_cost_breakdown_p.usage_start
                        AND c.namespace IS NOT DISTINCT FROM reporting_ocp_cost_breakdown_p.namespace
                        AND c.node IS NOT DISTINCT FROM reporting_ocp_cost_breakdown_p.node)
    GROUP BY 1
)
SELECT rtu.*, bd.bd_cost_value, bd.bd_distributed
FROM rtu LEFT JOIN bd ON bd.custom_name = rtu.custom_name
ORDER BY rtu.rtu_calculated + rtu.rtu_distributed DESC;
