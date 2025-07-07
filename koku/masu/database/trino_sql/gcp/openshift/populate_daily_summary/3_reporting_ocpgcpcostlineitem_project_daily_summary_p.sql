INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p (
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    tags,
    cost_category_id,
    source_uuid,
    credit_amount,
    invoice_month
)
with cte_pg_enabled_keys as (
    select array['vm_kubevirt_io_name'] || array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type IN ('GCP', 'OCP')
),
filtered_data as (
    SELECT
        cluster_id,
        cluster_alias,
        data_source,
        namespace,
        node,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        cast(
            map_filter(
                cast(json_parse(pod_labels) as map(varchar, varchar)),
                (k,v) -> contains(pek.keys, k)
            ) as json
        ) AS enabled_labels,
        resource_id,
        date(usage_start) as usage_start,
        account_id,
        project_id,
        project_name,
        instance_type,
        service_id,
        service_alias,
        CASE
            WHEN upper(data_transfer_direction) = 'IN' THEN
                -- GCP uses gibibyte but we are tracking this field in gigabytes
                CASE unit
                    WHEN 'gibibyte' THEN usage_amount * 1.07374
                    ELSE usage_amount
                END
            ELSE 0
        END as infrastructure_data_in_gigabytes,
        CASE
            WHEN upper(data_transfer_direction) = 'OUT' THEN
                -- GCP uses gibibyte but we are tracking this field in gigabytes
                CASE unit
                    WHEN 'gibibyte' THEN usage_amount * 1.07374
                    ELSE usage_amount
                END
            ELSE 0
        END as infrastructure_data_out_gigabytes,
        data_transfer_direction as data_transfer_direction,
        sku_id,
        sku_alias,
        region,
        unit,
        usage_amount,
        currency,
        unblended_cost,
        markup_cost,
        cost_category_id,
        credit_amount,
        invoice_month
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE source = {{cloud_provider_uuid}}
        AND ocp_source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND day IN {{days | inclause}}
)
SELECT
    uuid(),
    max({{report_period_id}}) as report_period_id,
    cluster_id,
    max(cluster_alias) as cluster_alias,
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
    max({{bill_id}}) as cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    SUM(fd.infrastructure_data_in_gigabytes) as infrastructure_data_in_gigabytes,
    SUM(fd.infrastructure_data_out_gigabytes) as infrastructure_data_out_gigabytes,
    MAX(data_transfer_direction) as data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    SUM(usage_amount),
    currency,
    SUM(unblended_cost),
    SUM(markup_cost),
    fd.enabled_labels as tags,
    cost_category_id,
    cast({{cloud_provider_uuid}} as UUID),
    SUM(credit_amount),
    invoice_month
FROM filtered_data as fd
GROUP BY
    usage_start,
    cluster_id,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    fd.enabled_labels,
    resource_id,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    cost_category_id,
    invoice_month,
    currency;
