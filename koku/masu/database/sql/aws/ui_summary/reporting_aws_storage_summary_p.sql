DELETE FROM {{schema | sqlsafe}}.reporting_aws_storage_summary_p
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
;

INSERT INTO {{schema | sqlsafe}}.reporting_aws_storage_summary_p (
    id,
    usage_start,
    usage_end,
    product_family,
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
    usage_start,
    usage_start as usage_end,
    product_family,
    sum(usage_amount) as usage_amount,
    max(unit) as unit,
    sum(unblended_cost) as unblended_cost,
    sum(blended_cost) as blended_cost,
    sum(coalesce(savingsplan_effective_cost, 0.0::numeric(24,9))) AS savingsplan_effective_cost,
    sum(coalesce(calculated_amortized_cost, 0.0::numeric(33,9))) AS calculated_amortized_cost,
    sum(markup_cost) as markup_cost,
    sum(coalesce(markup_cost_blended, 0.0::numeric(33,15))) AS markup_cost_blended,
    sum(coalesce(markup_cost_savingsplan, 0.0::numeric(33,15))) AS markup_cost_savingsplan,
    sum(coalesce(markup_cost_amortized, 0.0::numeric(33,9))) AS markup_cost_amortized,
    max(currency_code) as currency_code,
    {{source_uuid}}::uuid as source_uuid
FROM {{schema | sqlsafe}}.reporting_awscostentrylineitem_daily_summary
-- Get data for this month or last month
WHERE product_family LIKE '%%Storage%%'
    AND unit = 'GB-Mo'
    AND usage_start >= {{start_date}}::date
    AND usage_end <= {{end_date}}::date
    AND source_uuid = {{source_uuid}}
GROUP BY usage_start, product_family
;
