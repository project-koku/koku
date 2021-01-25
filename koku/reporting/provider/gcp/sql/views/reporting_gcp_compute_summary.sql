DROP INDEX IF EXISTS gcp_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_gcp_compute_summary;

CREATE MATERIALIZED VIEW reporting_gcp_compute_summary AS (
    SELECT ROW_NUMBER() OVER(ORDER BY usage_start, instance_type, source_uuid) AS id,
        usage_start,
        usage_start as usage_end,
        instance_type,
        SUM(case when usage_amount = 'NaN' then 0.0::numeric(24,9) else usage_amount end::numeric(24,9)) AS usage_amount,
        MAX(unit) AS unit,
        SUM(unblended_cost) AS unblended_cost,
        SUM(markup_cost) AS markup_cost,
        MAX(currency) AS currency,
        source_uuid
    FROM reporting_gcpcostentrylineitem_daily_summary
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
        AND instance_type IS NOT NULL
    GROUP BY usage_start, instance_type, source_uuid
)
WITH DATA
    ;

CREATE UNIQUE INDEX gcp_compute_summary
    ON reporting_gcp_compute_summary (usage_start, source_uuid, instance_type)
;
