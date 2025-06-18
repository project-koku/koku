DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS lids
WHERE lids.report_period_id = {{report_period_id}}
    AND lids.usage_start >= {{start_date}}::date
    AND lids.usage_start <= {{end_date}}::date
    {%- if rate_type is defined %}
    AND lids.cost_model_rate_type = {{rate_type}}
    {%- else %}
    AND lids.cost_model_rate_type IS NOT NULL
    {%- endif %}
    AND lids.monthly_cost_type = {{cost_type}}
;
