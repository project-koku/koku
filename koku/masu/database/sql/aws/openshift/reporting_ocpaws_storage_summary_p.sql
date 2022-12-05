DELETE FROM {{schema_name | sqlsafe}}.reporting_ocpaws_storage_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_end <= {{end_date}}::date
    AND cluster_id = {{cluster_id}}
    AND source_uuid = {{source_uuid}}::uuid
;

INSERT INTO {{schema_name | sqlsafe}}.reporting_ocpaws_storage_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    usage_account_id,
    account_alias_id,
    product_family,
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
        product_family,
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
    FROM {{schema_name | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p
    WHERE product_family LIKE '%%Storage%%'
        AND unit = 'GB-Mo'
        AND usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}
    GROUP BY usage_start, usage_account_id, account_alias_id, product_family
;
