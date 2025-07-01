-- insert managed table data into postgres table

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
with cte_pg_enabled_keys as (
    select array_agg(key order by key) as keys
      from postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
     where enabled = true
     and provider_type IN ('AWS', 'OCP')
)
SELECT uuid(),
    {{report_period_id | sqlsafe}} as report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    date(usage_start),
    date(usage_end),
    product_code,
    product_family,
    instance_type,
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
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
    json_parse(pod_labels),
    cast(
        map_filter(
            cast(json_parse(tags) as map(varchar, varchar)),
            (k,v) -> contains(pek.keys, k)
        ) as json
     ) AS tags,
    json_parse(aws_cost_category),
    cost_category_id,
    cast(source as UUID)
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary
CROSS JOIN cte_pg_enabled_keys AS pek
WHERE source = {{aws_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}}
    AND day IN {{days | inclause}}
;
