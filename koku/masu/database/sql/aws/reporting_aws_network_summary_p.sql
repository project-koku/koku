DELETE FROM {{schema | sqlsafe}}.reporting_aws_network_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;
INSERT INTO {{schema | sqlsafe}}.reporting_aws_network_summary_p (
    id,
    usage_start,
    usage_end,
    usage_account_id,
    account_alias_id,
    organizational_unit_id,
    product_code,
    usage_amount,
    unit,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    markup_cost,
    markup_cost_blended,
    markup_cost_savingsplan,
    currency_code,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        usage_account_id,
        max(account_alias_id) as account_alias_id,
        max(organizational_unit_id) as organizational_unit_id,
        product_code,
        sum(usage_amount) as usage_amount,
        max(unit) as unit,
        sum(unblended_cost) as unblended_cost,
        sum(blended_cost) as blended_cost,
        sum(coalesce(savingsplan_effective_cost, 0.0::numeric(24,9))) AS savingsplan_effective_cost,
        sum(markup_cost) as markup_cost,
        sum(coalesce(markup_cost_blended, 0.0::numeric(33,15))) AS markup_cost_blended,
        sum(coalesce(markup_cost_savingsplan, 0.0::numeric(33,15))) AS markup_cost_savingsplan,
        max(currency_code) as currency_code,
        {{source_uuid}}::uuid as source_uuid
    FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND product_code IN ('AmazonVPC','AmazonCloudFront','AmazonRoute53','AmazonAPIGateway')
    GROUP BY usage_start, usage_account_id, product_code
;
