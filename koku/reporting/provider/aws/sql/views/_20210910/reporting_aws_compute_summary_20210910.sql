DROP INDEX IF EXISTS aws_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_aws_compute_summary;

CREATE MATERIALIZED VIEW reporting_aws_compute_summary AS (
    SELECT ROW_NUMBER() OVER(ORDER BY c.usage_start, c.instance_type, c.source_uuid) AS id,
        c.usage_start,
        c.usage_start as usage_end,
        c.instance_type,
        r.resource_ids,
        CARDINALITY(r.resource_ids) AS resource_count,
        c.usage_amount,
        c.unit,
        c.unblended_cost,
        c.blended_cost,
        c.savingsplan_effective_cost,
        c.markup_cost,
        c.currency_code,
        c.source_uuid
    FROM (
        -- this group by gets the counts
        SELECT usage_start,
            instance_type,
            SUM(usage_amount) AS usage_amount,
            MAX(unit) AS unit,
            SUM(unblended_cost) AS unblended_cost,
            SUM(blended_cost) AS blended_cost,
            SUM(markup_cost) AS markup_cost,
            SUM(savingsplan_effective_cost) AS savingsplan_effective_cost,
            MAX(currency_code) AS currency_code,
            source_uuid
        FROM reporting_awscostentrylineitem_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
            AND instance_type IS NOT NULL
        GROUP BY usage_start, instance_type, source_uuid
    ) AS c
    JOIN (
        -- this group by gets the distinct resources running by day
        SELECT usage_start,
            instance_type,
            ARRAY_AGG(DISTINCT resource_id ORDER BY resource_id) as resource_ids
        FROM (
            SELECT usage_start,
                instance_type,
                UNNEST(resource_ids) AS resource_id
            FROM reporting_awscostentrylineitem_daily_summary
            WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
                AND instance_type IS NOT NULL
        ) AS x
        GROUP BY usage_start, instance_type
    ) AS r
    ON c.usage_start = r.usage_start
        AND c.instance_type = r.instance_type
)
WITH DATA
    ;

CREATE UNIQUE INDEX aws_compute_summary
    ON reporting_aws_compute_summary (usage_start, source_uuid, instance_type)
;
