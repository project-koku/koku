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
WITH collapsed_labels as (
    SELECT
        pds.row_uuid,
        CAST(
            MAP_FILTER(
                MAP_AGG(t.pod_label_key, t.pod_label_value),
                (k, v) -> k IS NOT NULL
            ) AS JSON
        ) AS consolidated_pod_label
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary as pds
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
    clabels.consolidated_pod_label as pod_labels,
    resource_id,
    date(usage_start),
    date(usage_end) as usage_end,
    MAX({{bill_id | sqlsafe}}) as cost_entry_bill_id,
    subscription_guid,
    MAX(subscription_name) as subscription_name,
    instance_type,
    service_name,
    SUM(CASE
        WHEN lower(data_transfer_direction) = 'datatrin' THEN usage_quantity
        ELSE 0
    END) as infrastructure_data_in_gigabytes,
    SUM(CASE
        WHEN lower(data_transfer_direction) = 'datatrout' THEN usage_quantity
        ELSE 0
    END) as infrastructure_data_out_gigabytes,
    CASE
        WHEN lower(data_transfer_direction) = 'datatrin' THEN 'IN'
        WHEN lower(data_transfer_direction) = 'datatrout' THEN 'OUT'
        ELSE NULL
    END as data_transfer_direction,
    resource_location,
    SUM(usage_quantity) as usage_quantity,
    MAX(unit_of_measure) as unit_of_measure,
    MAX(currency) as currency,
    SUM(pretax_cost) as pretax_cost,
    SUM(markup_cost) as markup_cost,
    clabels.consolidated_pod_label as tags,
    cost_category_id,
    cast(source as UUID) as source_uuid
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary as pds
LEFT JOIN collapsed_labels as clabels
    ON pds.row_uuid = clabels.row_uuid
WHERE source = {{cloud_provider_uuid}}
    AND ocp_source = {{ocp_provider_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}}
    AND day in {{days | inclause}}
GROUP BY
    usage_start,
    usage_end,
    cluster_id,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    clabels.consolidated_pod_label,
    resource_id,
    subscription_guid,
    instance_type,
    service_name,
    CASE
        WHEN lower(data_transfer_direction) = 'datatrin' THEN 'IN'
        WHEN lower(data_transfer_direction) = 'datatrout' THEN 'OUT'
        ELSE NULL
    END,
    resource_location,
    unit_of_measure,
    currency,
    cost_category_id,
    source;
