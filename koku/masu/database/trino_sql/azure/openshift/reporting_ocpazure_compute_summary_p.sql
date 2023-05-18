INSERT INTO postgres.{{schema_name | sqlsafe}}.reporting_ocpazure_compute_summary_p (
    id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    subscription_guid,
    instance_type,
    resource_id,
    usage_quantity,
    unit_of_measure,
    pretax_cost,
    markup_cost,
    currency,
    source_uuid
)
    SELECT uuid() as id,
        usage_start,
        usage_start as usage_end,
        max(cluster_id) as cluster_id,
        max(cluster_alias) as cluster_alias,
        subscription_guid,
        instance_type,
        resource_id,
        sum(usage_quantity) as usage_quantity,
        max(unit_of_measure) as unit_of_measure,
        sum(pretax_cost) as pretax_cost,
        sum(markup_cost) as markup_cost,
        max(currency) as currency,
        cast({{azure_source_uuid}} as uuid) as source_uuid
    FROM hive.{{schema_name | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary
    WHERE azure_source = {{azure_source_uuid}}
        AND ocp_source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day in {{days | inclause}}
        AND usage_start >= {{start_date}}
        AND usage_start <= date_add('day', 1, {{end_date}})
        AND instance_type IS NOT NULL
        AND unit_of_measure = 'Hrs'
    GROUP BY usage_start, subscription_guid, instance_type, resource_id
