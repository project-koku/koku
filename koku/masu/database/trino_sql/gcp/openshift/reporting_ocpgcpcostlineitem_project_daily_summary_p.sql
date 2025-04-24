-- insert managed table data into postgres

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
SELECT uuid(),
    {{report_period_id}} as report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    json_parse(pod_labels),
    resource_id,
    date(usage_start),
    date(usage_start) as usage_end,
    {{bill_id}} as cost_entry_bill_id,
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
    json_parse(tags),
    cost_category_id,
    cast(source as UUID),
    credit_amount,
    invoice_month
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary
WHERE source = {{gcp_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN {{days | inclause}}
;
