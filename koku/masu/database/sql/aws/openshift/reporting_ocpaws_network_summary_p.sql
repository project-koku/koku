INSERT INTO {{schema | sqlsafe}}.reporting_ocpaws_network_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    usage_account_id,
    account_alias_id,
    product_code,
    usage_amount,
    unit,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    currency_code,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        {{cluster_id}},
        {{cluster_alias}},
        usage_account_id,
        max(account_alias_id),
        product_code,
        sum(usage_amount),
        max(unit),
        sum(unblended_cost),
        sum(markup_cost),
        sum(blended_cost),
        sum(markup_cost_blended),
        sum(savingsplan_effective_cost),
        sum(markup_cost_savingsplan),
        max(currency_code),
        {{source_uuid}}::uuid
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p
    WHERE product_code IN ('AmazonVPC','AmazonCloudFront','AmazonRoute53','AmazonAPIGateway')
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY usage_start, usage_account_id, account_alias_id, product_code
;
