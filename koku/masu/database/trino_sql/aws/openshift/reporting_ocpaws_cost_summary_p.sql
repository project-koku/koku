INSERT INTO postgres.{{schema_name | sqlsafe}}.reporting_ocpaws_cost_summary_p (
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
    SELECT uuid() as id,
        usage_start,
        usage_start as usage_end,
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        sum(unblended_cost),
        sum(markup_cost),
        sum(blended_cost),
        sum(markup_cost_blended),
        sum(savingsplan_effective_cost),
        sum(markup_cost_savingsplan),
        max(currency_code),
        cast({{aws_source_uuid}} as uuid) as source_uuid,
        max(cost_category_id)
    FROM hive.{{schema_name | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary
    WHERE aws_source = {{aws_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
    GROUP BY usage_start
