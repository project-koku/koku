SELECT
    min(usage_start_time),
    max(usage_start_time)
    FROM {{schema | sqlsafe}}.gcp_line_items_daily
    WHERE
    -- Logic to extended start and end dates when running GCP summary at a month boundary.
    -- To catch cross over data we need to extend the start/end dates by a couple of days.
    -- This logic allows us to catch both 2025-07-31 and 2025-09-01 with the invoice 202508.
    usage_start_time >=
    CASE
        WHEN EXTRACT(DAY FROM DATE({{start_date}})) = 1 THEN DATE({{start_date}}) - INTERVAL '3 days'
        ELSE DATE({{start_date}})
    END
    AND usage_start_time <=
    CASE
        WHEN (DATE_TRUNC('month', DATE({{end_date}})) + INTERVAL '1 month' - INTERVAL '1 day')::date = DATE({{end_date}}) THEN DATE({{end_date}}) + INTERVAL '3 days'
        ELSE DATE({{end_date}})
    END
    AND invoice_month = {{invoice_month}}
    AND source = {{source_uuid}}
    AND (
        (year = EXTRACT(YEAR FROM DATE({{start_date}}))::VARCHAR AND month = LPAD(EXTRACT(MONTH FROM DATE({{start_date}}))::text, 2, '0'))
        OR
        (year = EXTRACT(YEAR FROM DATE({{end_date}}))::VARCHAR AND month = LPAD(EXTRACT(MONTH FROM DATE({{end_date}}))::text, 2, '0'))
        OR
        (year = EXTRACT(YEAR FROM DATE({{start_date}}) - INTERVAL '1 month')::VARCHAR AND month = LPAD(EXTRACT(MONTH FROM DATE({{start_date}}) - INTERVAL '1 month')::text, 2, '0'))
        OR
        (year = EXTRACT(YEAR FROM DATE({{end_date}}) + INTERVAL '1 month')::VARCHAR AND month = LPAD(EXTRACT(MONTH FROM DATE({{end_date}}) + INTERVAL '1 month')::text, 2, '0'))
    )
