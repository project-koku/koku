INSERT INTO {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_p (
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
with cte_pg_enabled_keys as (
    select array['vm_kubevirt_io_name'] || array_agg(key order by key) as keys
      from {{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type IN ('AWS', 'OCP')
),
filtered_data as (
    SELECT cluster_id,
    cast(
        map_filter(
            cast(json_parse(tags) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
     ) AS enabled_tags,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    date(usage_start) as usage_start,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    CASE
        WHEN upper(data_transfer_direction) = 'IN' THEN usage_amount
        ELSE 0
    END AS infrastructure_data_in_gigabytes,
    CASE
        WHEN upper(data_transfer_direction) = 'OUT' THEN usage_amount
        ELSE 0
    END AS infrastructure_data_out_gigabytes,
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
    json_parse(aws_cost_category) as aws_cost_category,
    cost_category_id
FROM {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary
CROSS JOIN cte_pg_enabled_keys AS pek
WHERE source = {{cloud_provider_uuid}}
    AND ocp_source = {{ocp_provider_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN {{days | inclause}}
)
SELECT
    uuid_generate_v4(),
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
    fd.usage_start as usage_start,
    fd.usage_start as usage_end,
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
    SUM(fd.infrastructure_data_in_gigabytes) as infrastructure_data_in_gigabytes,
    SUM(fd.infrastructure_data_out_gigabytes) as infrastructure_data_out_gigabytes,
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
    fd.enabled_tags as pod_labels,
    fd.enabled_tags as tags,
    fd.aws_cost_category as aws_cost_category,
    cost_category_id,
    {{cloud_provider_uuid}}::uuid as source_uuid
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
    fd.enabled_tags,
    fd.aws_cost_category,
    cost_category_id;
