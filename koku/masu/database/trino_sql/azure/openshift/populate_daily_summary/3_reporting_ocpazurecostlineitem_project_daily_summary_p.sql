INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_p (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    pod_labels,
    resource_id,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    subscription_guid,
    subscription_name,
    instance_type,
    service_name,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    data_transfer_direction,
    resource_location,
    usage_quantity,
    unit_of_measure,
    currency,
    pretax_cost,
    markup_cost,
    tags,
    cost_category_id,
    source_uuid
)
with cte_pg_enabled_keys as (
    select array['vm_kubevirt_io_name'] || array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type IN ('Azure', 'OCP')
),
filtered_data as (
    SELECT cluster_id as cluster_id,
        cluster_alias as cluster_alias,
        data_source,
        namespace,
        node,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        resource_id,
        date(usage_start) as usage_start,
        date(usage_end),
        subscription_guid,
        subscription_name,
        instance_type,
        service_name,
        CASE
            WHEN lower(data_transfer_direction) = 'datatrin' THEN usage_quantity
            ELSE 0
        END as infrastructure_data_in_gigabytes,
        CASE
            WHEN lower(data_transfer_direction) = 'datatrout' THEN usage_quantity
            ELSE 0
        END as infrastructure_data_out_gigabytes,
        -- gives each row a unique identifier for group by during back populate
        CASE
            WHEN lower(data_transfer_direction) = 'datatrin' THEN 'IN'
            WHEN lower(data_transfer_direction) = 'datatrout' THEN 'OUT'
            ELSE NULL
        END as data_transfer_direction,
        resource_location,
        usage_quantity,
        unit_of_measure,
        currency,
        pretax_cost,
        markup_cost,
        cast(
            map_filter(
                cast(json_parse(tags) as map(varchar, varchar)),
                (k,v) -> contains(pek.keys, k)
            ) as json
        ) AS enabled_labels,
        cost_category_id
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE source = {{cloud_provider_uuid}}
        AND ocp_source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}}
        AND day in {{days | inclause}}
)
SELECT
    uuid(),
    MAX({{report_period_id | sqlsafe}}) as report_period_id,
    cluster_id,
    MAX(cluster_alias) as cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    fd.enabled_labels as pod_labels,
    resource_id,
    fd.usage_start as usage_start,
    fd.usage_start as usage_end,
    MAX({{bill_id | sqlsafe}}) as cost_entry_bill_id,
    subscription_guid,
    MAX(subscription_name) as subscription_name,
    instance_type,
    service_name,
    SUM(fd.infrastructure_data_in_gigabytes) as infrastructure_data_in_gigabytes,
    SUM(fd.infrastructure_data_out_gigabytes) as  infrastructure_data_out_gigabytes,
    fd.data_transfer_direction as data_transfer_direction,
    resource_location,
    SUM(usage_quantity) as usage_quantity,
    MAX(unit_of_measure) as unit_of_measure,
    MAX(currency) as currency,
    SUM(pretax_cost) as pretax_cost,
    SUM(markup_cost) as markup_cost,
    fd.enabled_labels as tags,
    cost_category_id,
    cast({{cloud_provider_uuid}} as UUID) as source_uuid
FROM filtered_data as fd
GROUP BY
    fd.usage_start,
    cluster_id,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    fd.enabled_labels,
    resource_id,
    subscription_guid,
    instance_type,
    service_name,
    fd.data_transfer_direction,
    resource_location,
    unit_of_measure,
    currency,
    cost_category_id;
