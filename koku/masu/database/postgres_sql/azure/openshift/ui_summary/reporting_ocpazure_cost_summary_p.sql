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
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{azure_source_uuid}}::uuid as source_uuid,
        max(cost_category_id) as cost_category_id
    FROM {{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
    WHERE source = {{azure_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= {{end_date}} + INTERVAL '1 day'
    GROUP BY usage_start
