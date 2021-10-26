DELETE FROM {{schema | sqlsafe}}.reporting_aws_compute_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_aws_compute_summary_p (
    id,
    usage_start,
    usage_end,
    instance_type,
    resource_ids,
    resource_count,
    usage_amount,
    unit,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    markup_cost,
    currency_code,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
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
            {{source_uuid}}::uuid as source_uuid
        FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
        WHERE usage_start >= {{start_date}}::date
            AND usage_start <= {{end_date}}::date
            AND instance_type IS NOT NULL
            AND source_uuid = {{source_uuid}}
        GROUP BY usage_start, instance_type
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
            FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
            WHERE usage_start >= {{start_date}}::date
                AND usage_start <= {{end_date}}::date
                AND instance_type IS NOT NULL
                AND source_uuid = {{source_uuid}}
        ) AS x
        GROUP BY usage_start, instance_type
    ) AS r
    ON c.usage_start = r.usage_start
        AND c.instance_type = r.instance_type
;
