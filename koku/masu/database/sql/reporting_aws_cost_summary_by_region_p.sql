DELETE FROM {{schema | sqlsafe}}.reporting_aws_cost_summary_by_region_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid_id = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_aws_cost_summary_by_region_p
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        max(organizational_unit_id) as organizational_unit_id,
        region,
        availability_zone,
        sum(unblended_cost) as unblended_cost,
        sum(savingsplan_effective_cost) as savingsplan_effective_cost,
        sum(markup_cost) as markup_cost,
        max(currency_code) as currency_code,
        max(source_uuid::text)::uuid as source_uuid
    FROM reporting_awscostentrylineitem_daily_summary
    -- Get data for this month or last month
    WHERE usage_start >= DATE_TRUNC('month', NOW() - '2 month'::interval)::date
    GROUP BY usage_start, usage_account_id, region, availability_zone
;
