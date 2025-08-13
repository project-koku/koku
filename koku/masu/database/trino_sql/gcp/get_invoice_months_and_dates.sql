SELECT
    invoice_month, min(usage_start_time), max(usage_start_time)
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily
    WHERE usage_start_time >= {{start_date}}
    AND usage_start_time <= {{end_date}}
    AND source = {{source_uuid}}
    AND (
        month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}})) AS VARCHAR), 2, '0')
        OR month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}}) - INTERVAL '1' MONTH) AS VARCHAR), 2, '0')
    )
    AND (
        year = CAST(EXTRACT(YEAR FROM DATE({{start_date}})) AS VARCHAR)
        OR YEAR = CAST(EXTRACT(YEAR FROM DATE({{end_date}})) AS VARCHAR)
    )
    group by invoice_month
