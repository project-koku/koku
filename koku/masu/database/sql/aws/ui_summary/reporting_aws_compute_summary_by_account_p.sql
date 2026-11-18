DELETE FROM {{schema | sqlsafe}}.reporting_aws_compute_summary_by_account_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_aws_compute_summary_by_account_p (
    id,
    usage_start,
    usage_end,
    usage_account_id,
    account_alias_id,
    organizational_unit_id,
    instance_type,
    resource_ids,
    resource_count,
    usage_amount,
    unit,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    calculated_amortized_cost,
    markup_cost,
    markup_cost_blended,
    markup_cost_savingsplan,
    markup_cost_amortized,
    currency_code,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        c.usage_start,
        c.usage_start AS usage_end,
        c.usage_account_id,
        c.account_alias_id,
        c.organizational_unit_id,
        c.instance_type,
        r.resource_ids,
        CARDINALITY(r.resource_ids) AS resource_count,
        c.usage_amount,
        c.unit,
        c.unblended_cost,
        c.blended_cost,
        c.savingsplan_effective_cost,
        c.calculated_amortized_cost,
        c.markup_cost,
        c.markup_cost_blended,
        c.markup_cost_savingsplan,
        c.markup_cost_amortized,
        c.currency_code,
        c.source_uuid
    FROM (
        -- this group by gets the counts
        SELECT usage_start,
            usage_account_id,
            MAX(account_alias_id) as account_alias_id,
            MAX(organizational_unit_id) as organizational_unit_id,
            instance_type,
            SUM(usage_amount) AS usage_amount,
            MAX(unit) AS unit,
            SUM(unblended_cost) AS unblended_cost,
            SUM(blended_cost) AS blended_cost,
            SUM(coalesce(savingsplan_effective_cost, 0.0::numeric(24,9))) AS savingsplan_effective_cost,
            SUM(coalesce(calculated_amortized_cost, 0.0::numeric(33,9))) AS calculated_amortized_cost,
            SUM(markup_cost) AS markup_cost,
            SUM(coalesce(markup_cost_blended, 0.0::numeric(33,15))) AS markup_cost_blended,
            SUM(coalesce(markup_cost_savingsplan, 0.0::numeric(33,15))) AS markup_cost_savingsplan,
            SUM(coalesce(markup_cost_amortized, 0.0::numeric(33,9))) AS markup_cost_amortized,
            MAX(currency_code) AS currency_code,
            {{source_uuid}}::uuid as source_uuid
        FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
        WHERE usage_start >= {{start_date}}::date
            AND usage_start <= {{end_date}}::date
            AND instance_type IS NOT NULL
            AND source_uuid = {{source_uuid}}
        GROUP BY usage_start, usage_account_id, instance_type
    ) AS c
    JOIN (
        -- this group by gets the distinct resources running by day
        SELECT usage_start,
            usage_account_id,
            max(account_alias_id) as account_alias_id,
            instance_type,
            array_agg(distinct resource_id order by resource_id) as resource_ids
        FROM (
            SELECT usage_start,
                usage_account_id,
                account_alias_id,
                instance_type,
                UNNEST(resource_ids) as resource_id
            FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
            WHERE usage_start >= {{start_date}}::date
                AND usage_start <= {{end_date}}::date
                AND instance_type IS NOT NULL
                AND source_uuid = {{source_uuid}}
        ) AS x
        GROUP BY usage_start, usage_account_id, instance_type
    ) AS r
        ON c.usage_start = r.usage_start
            AND c.instance_type = r.instance_type
            AND c.usage_account_id = r.usage_account_id
;
