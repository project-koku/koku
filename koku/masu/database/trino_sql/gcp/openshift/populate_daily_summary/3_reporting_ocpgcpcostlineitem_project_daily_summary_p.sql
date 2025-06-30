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
WITH collapsed_labels as (
    SELECT
        pds.row_uuid,
        CAST(
            MAP_FILTER(
                MAP_AGG(t.pod_label_key, t.pod_label_value),
                (k, v) -> k IS NOT NULL
            ) AS JSON
        ) AS consolidated_pod_label
    FROM
        hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary AS pds
    LEFT JOIN UNNEST(CAST(JSON_PARSE(pds.pod_labels) AS MAP(VARCHAR, VARCHAR))) AS t(pod_label_key, pod_label_value) ON TRUE
    WHERE
        pds.pod_labels IS NOT NULL AND pds.pod_labels != '{}'
    AND pds.ocp_source = {{ocp_provider_uuid}}
    AND pds.year = {{year}}
    AND pds.month = {{month}}
    AND pds.source = {{cloud_provider_uuid}}
    GROUP BY
        pds.row_uuid
)
SELECT uuid(),
    max({{report_period_id}}) as report_period_id,
    cluster_id,
    max(cluster_alias) as cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    clabels.consolidated_pod_label as pod_labels,
    resource_id,
    date(usage_start),
    date(usage_start) as usage_end,
    max({{bill_id}}) as cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    SUM(CASE
        WHEN upper(data_transfer_direction) = 'IN' THEN
            -- GCP uses gibibyte but we are tracking this field in gigabytes
            CASE unit
                WHEN 'gibibyte' THEN usage_amount * 1.07374
                ELSE usage_amount
            END
        ELSE 0
    END) as infrastructure_data_in_gigabytes,
    SUM(CASE
        WHEN upper(data_transfer_direction) = 'OUT' THEN
            -- GCP uses gibibyte but we are tracking this field in gigabytes
            CASE unit
                WHEN 'gibibyte' THEN usage_amount * 1.07374
                ELSE usage_amount
            END
        ELSE 0
    END) as infrastructure_data_out_gigabytes,
    MAX(data_transfer_direction) as data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    SUM(usage_amount),
    currency,
    SUM(unblended_cost),
    SUM(markup_cost),
    clabels.consolidated_pod_label as tags,
    cost_category_id,
    cast(source as UUID),
    SUM(credit_amount),
    invoice_month
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary as pds
LEFT JOIN collapsed_labels as clabels
    ON pds.row_uuid = clabels.row_uuid
WHERE source = {{cloud_provider_uuid}}
    AND ocp_source = {{ocp_provider_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN {{days | inclause}}
GROUP BY
    usage_start,
    cluster_id,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    clabels.consolidated_pod_label,
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
    source,
    invoice_month,
    currency
;
