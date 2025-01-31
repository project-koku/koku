CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily
(
    invoice_month varchar,
    billing_account_id varchar,
    project_id varchar,
    usage_start_time timestamp(3),
    service_id varchar,
    sku_id varchar,
    system_labels varchar,
    labels varchar,
    cost_type varchar,
    location_region varchar,
    resource_name varchar,
    project_name varchar,
    service_description varchar,
    sku_description varchar,
    usage_pricing_unit varchar,
    usage_amount_in_pricing_units double,
    currency varchar,
    cost double,
    daily_credits double,
    resource_global_name varchar,
    resource_id_matched boolean,
    matched_tag varchar,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;

-- Note: We can remove the need for this table if we add in uuid during parquet creation
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_gcp_uuid_temp
(
    row_uuid varchar,
    invoice_month varchar,
    billing_account_id varchar,
    project_id varchar,
    usage_start_time timestamp(3),
    service_id varchar,
    sku_id varchar,
    system_labels varchar,
    labels varchar,
    cost_type varchar,
    location_region varchar,
    resource_name varchar,
    project_name varchar,
    service_description varchar,
    sku_description varchar,
    usage_pricing_unit varchar,
    usage_amount_in_pricing_units double,
    currency varchar,
    cost double,
    daily_credits double,
    resource_global_name varchar,
    source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(
    format = 'PARQUET',
    partitioned_by=ARRAY['source', 'year', 'month', 'day']
);

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp
(
    row_uuid varchar,
    invoice_month varchar,
    billing_account_id varchar,
    project_id varchar,
    usage_start_time timestamp(3),
    service_id varchar,
    sku_id varchar,
    system_labels varchar,
    labels varchar,
    cost_type varchar,
    location_region varchar,
    resource_name varchar,
    project_name varchar,
    service_description varchar,
    sku_description varchar,
    usage_pricing_unit varchar,
    usage_amount_in_pricing_units double,
    currency varchar,
    cost double,
    daily_credits double,
    resource_global_name varchar,
    resource_id_matched boolean,
    matched_tag varchar,
    ocp_source varchar,
    source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(
    format = 'PARQUET',
    partitioned_by=ARRAY['ocp_source', 'source', 'year', 'month', 'day']
);

DELETE FROM hive.{{schema | sqlsafe}}.managed_gcp_uuid_temp
WHERE source = {{cloud_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
;

-- Populate the possible rows of GCP data assigning a uuid to each row
INSERT INTO hive.{{schema | sqlsafe}}.managed_gcp_uuid_temp (
    row_uuid,
    invoice_month,
    billing_account_id,
    project_id,
    usage_start_time,
    service_id,
    sku_id,
    system_labels,
    labels,
    cost_type,
    location_region,
    resource_name,
    project_name,
    service_description,
    sku_description,
    usage_pricing_unit,
    usage_amount_in_pricing_units,
    currency,
    cost,
    daily_credits,
    resource_global_name,
    source,
    year,
    month,
    day
)
SELECT cast(uuid() as varchar) as row_uuid,
    gcp.invoice_month,
    gcp.billing_account_id,
    gcp.project_id,
    gcp.usage_start_time,
    gcp.service_id,
    gcp.sku_id,
    gcp.system_labels,
    gcp.labels,
    gcp.cost_type,
    gcp.location_region,
    gcp.resource_name,
    gcp.project_name,
    gcp.service_description,
    gcp.sku_description,
    gcp.usage_pricing_unit,
    gcp.usage_amount_in_pricing_units,
    gcp.currency,
    gcp.cost,
    gcp.daily_credits,
    gcp.resource_global_name,
    gcp.source as source,
    gcp.year,
    gcp.month,
    cast(day(gcp.usage_start_time) as varchar) as day
FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
WHERE gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month= {{month}}
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}});
