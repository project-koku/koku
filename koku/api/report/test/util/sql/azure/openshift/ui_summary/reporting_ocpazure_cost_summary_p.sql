-- This file allows us to mimic our trino logic to
-- populate the postgresql summary tables for unit testing.

INSERT INTO {{schema | sqlsafe}}.reporting_ocpazure_cost_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    pretax_cost,
    markup_cost,
    currency,
    source_uuid,
    cost_category_id
)
    SELECT uuid_generate_v4() as id,
        usage_start as usage_start,
        usage_start as usage_end,
        {{cluster_id}},
        {{cluster_alias}},
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id
    FROM {{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_p
    WHERE usage_start >= {{start_date}}::date
        AND usage_start <= {{end_date}}::date
        AND source_uuid = {{source_uuid}}
        AND cluster_id = {{cluster_id}}
    GROUP BY usage_start
;
