DELETE FROM {{schema | sqlsafe}}.reporting_azure_compute_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO reporting_azure_compute_summary_p (
    id,
    usage_start,
    usage_end,
    subscription_guid,
    instance_type,
    instance_ids,
    instance_count,
    usage_quantity,
    unit_of_measure,
    pretax_cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
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
        {{source_uuid}}::uuid as source_uuid
    FROM (
        -- this group by gets the counts
        SELECT usage_start,
            subscription_guid,
            instance_type,
            SUM(usage_quantity) AS usage_quantity,
            MAX(unit_of_measure) AS unit_of_measure,
            SUM(pretax_cost) AS pretax_cost,
            SUM(markup_cost) AS markup_cost,
            MAX(currency) AS currency
        FROM reporting_azurecostentrylineitem_daily_summary
        WHERE usage_start >= {{start_date}}::date
            AND usage_start <= {{end_date}}::date
            AND source_uuid = {{source_uuid}}
            AND instance_type IS NOT NULL
            AND unit_of_measure = 'Hrs'
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
            WHERE usage_start >= {{start_date}}::date
                AND usage_start <= {{end_date}}::date
                AND source_uuid = {{source_uuid}}
                AND instance_type IS NOT NULL
        ) AS x
        GROUP BY usage_start, subscription_guid, instance_type
    ) AS r
        ON c.usage_start = r.usage_start
            AND c.subscription_guid = r.subscription_guid
            AND c.instance_type = r.instance_type
;
