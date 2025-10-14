-- This file allows us to mimic our trino logic to
-- populate the postgresql summary tables for unit testing.

INSERT INTO {{schema | sqlsafe}}.reporting_ocpaws_cost_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    currency_code,
    source_uuid,
    cost_category_id
)
    SELECT uuid_generate_v4() as id,
        usage_start,
        usage_start as usage_end,
        {{cluster_id}},
        {{cluster_alias}},
        sum(unblended_cost),
        sum(markup_cost),
        sum(blended_cost),
        sum(markup_cost_blended),
        sum(savingsplan_effective_cost),
        sum(markup_cost_savingsplan),
        max(currency_code),
        {{source_uuid}}::uuid,
        max(cost_category_id)
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND cluster_id = {{cluster_id}}
        AND source_uuid = {{source_uuid}}::uuid
    GROUP BY usage_start
;
