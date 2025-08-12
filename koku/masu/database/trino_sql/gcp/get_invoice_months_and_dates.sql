SELECT
    invoice_month, min(usage_start_time), max(usage_start_time)
    FROM gcp_line_items_daily
    WHERE usage_start_time > {{start_date}}
    AND usage_start_time <= {{end_date}}
    group by invoice_month
