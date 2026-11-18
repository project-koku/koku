INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazure_cost_summary_p (
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
    SELECT uuid() as id,
        usage_start as usage_start,
        usage_start as usage_end,
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        cast({{azure_source_uuid}} as uuid) as source_uuid,
        max(cost_category_id) as cost_category_id
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
    WHERE source = {{azure_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
    GROUP BY usage_start
