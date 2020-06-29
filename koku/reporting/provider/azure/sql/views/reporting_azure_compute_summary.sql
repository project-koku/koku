DROP INDEX IF EXISTS azure_compute_summary;
DROP MATERIALIZED VIEW IF EXISTS reporting_azure_compute_summary;

CREATE MATERIALIZED VIEW reporting_azure_compute_summary AS(
    SELECT ROW_NUMBER() OVER(ORDER BY c.usage_start, c.subscription_guid, c.instance_type) AS id,
        c.usage_start,
        c.usage_start as usage_end,
        c.subscription_guid,
        c.instance_type,
        r.instance_ids,
        CARDINALITY(r.instance_ids) AS instance_count,
        c.usage_quantity,
        c.unit_of_measure,
        c.pretax_cost,
        c.markup_cost,
        c.currency,
        c.source_uuid
    FROM (
        -- this group by gets the counts
        SELECT usage_start,
            subscription_guid,
            instance_type,
            SUM(usage_quantity) AS usage_quantity,
            MAX(unit_of_measure) AS unit_of_measure,
            SUM(pretax_cost) AS pretax_cost,
            SUM(markup_cost) AS markup_cost,
            MAX(currency) AS currency,
            max(source_uuid::text)::uuid as source_uuid
        FROM reporting_azurecostentrylineitem_daily_summary
        WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
            AND instance_type IS NOT NULL
        GROUP BY usage_start, subscription_guid, instance_type
    ) AS c
    JOIN (
        -- this group by gets the distinct resources running by day
        SELECT usage_start,
            subscription_guid,
            instance_type,
            ARRAY_AGG(DISTINCT instance_id ORDER BY instance_id) as instance_ids
        FROM (
            SELECT usage_start,
                subscription_guid,
                instance_type,
                UNNEST(instance_ids) AS instance_id
            FROM reporting_azurecostentrylineitem_daily_summary
            WHERE usage_start >= DATE_TRUNC('month', NOW() - '1 month'::interval)::date
                AND instance_type IS NOT NULL
        ) AS x
        GROUP BY usage_start, subscription_guid, instance_type
    ) AS r
        ON c.usage_start = r.usage_start
            AND c.subscription_guid = r.subscription_guid
            AND c.instance_type = r.instance_type
)
WITH DATA
;

CREATE UNIQUE INDEX azure_compute_summary
    ON reporting_azure_compute_summary (usage_start, subscription_guid, instance_type)
;
