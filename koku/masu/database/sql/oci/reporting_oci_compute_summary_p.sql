DELETE FROM {{schema_name | sqlsafe}}.reporting_oci_compute_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema_name | sqlsafe}}.reporting_oci_compute_summary_p (
    id,
    usage_start,
    usage_end,
    usage_amount,
    instance_type,
    resource_ids,
    resource_count,
    unit,
    cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        c.usage_start,
        c.usage_start as usage_end,
        c.usage_amount,
        c.instance_type,
        r.resource_ids,
        CARDINALITY(r.resource_ids) AS resource_count,
        c.unit,
        c.cost,
        c.markup_cost,
        c.currency,
        c.source_uuid
    FROM (
        -- this group by gets the counts
        SELECT usage_start,
            SUM(usage_amount) AS usage_amount,
            MAX(unit) AS unit,
            SUM(cost) AS cost,
            SUM(markup_cost) AS markup_cost,
            MAX(currency) AS currency,
            instance_type,
            {{source_uuid}}::uuid as source_uuid
        FROM {{schema_name | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary
        WHERE usage_start >= {{start_date}}::date
            AND usage_start <= {{end_date}}::date
            AND source_uuid = {{source_uuid}}
        GROUP BY usage_start, instance_type
    ) AS c
    JOIN (
        -- this group by gets the distinct resources running by day
        SELECT usage_start,
            ARRAY_AGG(DISTINCT resource_id ORDER BY resource_id) as resource_ids
        FROM (
            SELECT usage_start,
                UNNEST(resource_ids) AS resource_id
            FROM {{schema_name | sqlsafe}}.reporting_ocicostentrylineitem_daily_summary
            WHERE usage_start >= {{start_date}}::date
                AND usage_start <= {{end_date}}::date
                AND source_uuid = {{source_uuid}}
        ) AS x
        GROUP BY usage_start
    ) AS r
    ON c.usage_start = r.usage_start
;
