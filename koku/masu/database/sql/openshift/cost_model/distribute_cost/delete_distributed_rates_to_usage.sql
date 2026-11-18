-- Delete distributed rows from rates_to_usage before re-inserting.
-- Mirrors delete_monthly_cost_model_rate_type.sql but targets RTU.
DELETE FROM {{schema | sqlsafe}}.rates_to_usage AS rtu
WHERE rtu.usage_start >= {{start_date}}::date
    AND rtu.usage_start <= {{end_date}}::date
    AND rtu.report_period_id = {{report_period_id}}
    AND rtu.monthly_cost_type = {{cost_model_rate_type}}
;
