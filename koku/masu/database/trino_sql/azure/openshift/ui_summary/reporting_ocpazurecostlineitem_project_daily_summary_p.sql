-- insert managed table data into postgres table

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
)
SELECT uuid(),
    {{report_period_id | sqlsafe}} as report_period_id,
    cluster_id as cluster_id,
    cluster_alias as cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    json_parse(pod_labels),
    resource_id,
    date(usage_start),
    date(usage_end),
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
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
     ) AS tags,
    cost_category_id,
    cast(source as UUID)
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
CROSS JOIN cte_pg_enabled_keys AS pek
WHERE source = {{azure_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day in {{days | inclause}}
;
