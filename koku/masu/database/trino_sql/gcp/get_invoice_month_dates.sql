SELECT
    min(usage_start_time),
    max(usage_start_time)
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily
    WHERE
    -- Logic to extended start and end dates when running GCP summary at a month boundary.
    -- To catch cross over data we need to extend the start/end dates by a couple of days.
    -- This logic allows us to catch both 2025-07-31 and 2025-09-01 with the invoice 202508.
    usage_start_time >=
    CASE
        WHEN DAY(DATE({{start_date}})) = 1 THEN DATE({{start_date}}) - INTERVAL '3' DAY
        ELSE DATE({{start_date}})
    END
    AND usage_start_time <=
    CASE
        WHEN LAST_DAY_OF_MONTH(DATE({{end_date}})) = DATE({{end_date}}) THEN DATE({{end_date}}) + INTERVAL '3' DAY
        ELSE DATE({{end_date}})
    END
    AND invoice_month = {{invoice_month}}
    AND source = {{source_uuid}}
    AND (
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}})) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}})) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}}) + INTERVAL '1' MONTH) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}}) + INTERVAL '1' MONTH) AS VARCHAR), 2, '0'))
    )
