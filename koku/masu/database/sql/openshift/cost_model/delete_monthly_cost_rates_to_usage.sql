-- Delete stale monthly-cost rows from rates_to_usage before re-inserting.
--
-- No rate_type filter, matching delete_monthly_cost.sql: a rate's
-- Infrastructure/Supplementary classification can change between runs, so all
-- rows for this monthly_cost_type must be cleared regardless of their
-- previously-recorded cost_model_rate_type.
DELETE FROM {{schema | sqlsafe}}.rates_to_usage AS rtu
WHERE rtu.usage_start >= {{start_date}}::date
    AND rtu.usage_start <= {{end_date}}::date
    AND rtu.report_period_id = {{report_period_id}}
    AND rtu.monthly_cost_type = {{cost_type}}
;
