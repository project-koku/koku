INSERT INTO {{schema | sqlsafe}}.reporting_ocpazure_cost_summary_by_service_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    subscription_guid,
    subscription_name,
    service_name,
    pretax_cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid_generate_v4() as id,
        usage_start as usage_start,
        usage_start as usage_end,
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        subscription_guid,
        max(subscription_name),
        service_name,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        {{azure_source_uuid}}::uuid as source_uuid
    FROM {{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
    WHERE source = {{azure_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= {{end_date}} + INTERVAL '1 day'
    GROUP BY usage_start, subscription_guid, service_name
