DROP INDEX IF EXISTS gcp_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_compute_summary;

CREATE MATERIALIZED VIEW reporting_gcp_compute_summary AS (
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, instance_type, source_uuid) AS id,
        usage_start,
        usage_start as usage_end,
        instance_type,
        sum(usage_amount) as usage_amount,
        MAX(unit) AS unit,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        MAX(currency) AS currency,
        source_uuid,
        invoice_month,
        SUM(credit_amount) AS credit_amount
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
        AND instance_type IS NOT NULL
    GROUP BY usage_start, instance_type, source_uuid, invoice_month
)
WITH DATA
    ;

CREATE UNIQUE INDEX gcp_compute_summary
    ON reporting_gcp_compute_summary (usage_start, source_uuid, instance_type, invoice_month)
;

-- Example of Credits:
-- [{'name': 'FreeTrial:Credit-018984-D0AAA4-940B88', 'amount': -1e-06, 'full_name': None, 'id': 'FreeTrial:Credit-018984-D0AAA4-940B88', 'type': 'PROMOTION'}]

-- Example of json build
-- json_build_object(
--     'cpu', sum(((coalesce(supplementary_monthly_cost_json, '{"cpu": 0}'::jsonb))->>'cpu')::decimal),
--     'memory', sum(((coalesce(supplementary_monthly_cost_json, '{"memory": 0}'::jsonb))->>'memory')::decimal),
--     'pvc', sum(((coalesce(supplementary_monthly_cost_json, '{"pvc": 0}'::jsonb))->>'pvc')::decimal)
-- ) as supplementary_monthly_cost_json,

-- Postgresql
-- SUM(CASE
-- WHEN credits != '{}'
-- THEN
--     (CAST(cost * 1000000 as DECIMAL(24,9)) +
--     ((CAST(json_extract_scalar(json_parse(credits), '$["amount"]') as DECIMAL(24,9)) * 1000000))) / 1000000
-- ELSE
--     cast(cost AS decimal(24,9)) --unblended cost if no credits
-- END) AS blended_cost
