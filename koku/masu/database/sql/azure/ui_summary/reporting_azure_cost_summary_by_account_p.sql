DELETE FROM {{schema | sqlsafe}}.reporting_azure_cost_summary_by_account_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_azure_cost_summary_by_account_p (
    id,
    usage_start,
    usage_end,
    subscription_guid,
    pretax_cost,
    markup_cost,
    currency,
    source_uuid,
    subscription_name
)
    SELECT uuid_generate_v4() as id,
        usage_start as usage_start,
        usage_start as usage_end,
        subscription_guid,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{source_uuid}}::uuid as source_uuid,
        subscription_name
    FROM {{schema | sqlsafe}}.reporting_azurecostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
    GROUP BY usage_start, subscription_guid, subscription_name
;
