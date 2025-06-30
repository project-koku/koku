INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p (
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
    resource_id,
    usage_start,
    usage_end,
    product_code,
    product_family,
    instance_type,
    cost_entry_bill_id,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    data_transfer_direction,
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    calculated_amortized_cost,
    markup_cost_amortized,
    pod_labels,
    tags,
    aws_cost_category,
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
    FROM
        hive.{{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary AS pds
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
    resource_id,
    date(usage_start),
    date(usage_end) as usage_end,
    product_code,
    product_family,
    instance_type,
    MAX({{bill_id | sqlsafe}}) as cost_entry_bill_id,
    usage_account_id,
    MAX(account_alias_id) as account_alias_id,
    availability_zone,
    region,
    unit,
    SUM(usage_amount) as usage_amount,
    SUM(CASE
        WHEN upper(data_transfer_direction) = 'IN' THEN usage_amount
        ELSE 0
    END) AS infrastructure_data_in_gigabytes,
    SUM(CASE
        WHEN upper(data_transfer_direction) = 'OUT' THEN usage_amount
        ELSE 0
    END) AS infrastructure_data_out_gigabytes,
    data_transfer_direction,
    MAX(currency_code) as currency_code,
    SUM(unblended_cost) as unblended_cost,
    SUM(markup_cost) as markup_cost,
    SUM(blended_cost) as blended_cost,
    SUM(markup_cost_blended) as markup_cost_blended,
    SUM(savingsplan_effective_cost) as savingsplan_effective_cost,
    SUM(markup_cost_savingsplan) as markup_cost_savingsplan,
    SUM(calculated_amortized_cost) as calculated_amortized_cost,
    SUM(markup_cost_amortized) as markup_cost_amortized,
    clabels.consolidated_pod_label as pod_labels,
    clabels.consolidated_pod_label as tags,
    json_parse(aws_cost_category),
    cost_category_id,
    cast(source as UUID) as source_uuid
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary as pds
LEFT JOIN collapsed_labels as clabels
    ON pds.row_uuid = clabels.row_uuid
WHERE source = {{cloud_provider_uuid}}
    AND ocp_source = {{ocp_provider_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}}
    AND day IN {{days | inclause}}
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
    resource_id,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    availability_zone,
    region,
    unit,
    data_transfer_direction,
    currency_code,
    clabels.consolidated_pod_label,
    json_parse(aws_cost_category),
    cost_category_id,
    source;
