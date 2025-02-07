CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_uuid_temp
(
    row_uuid varchar,
    additionalinfo varchar,
    billingcurrency varchar,
    billingcurrencycode varchar,
    consumedservice varchar,
    costinbillingcurrency double,
    date timestamp(3),
    metercategory varchar,
    metername varchar,
    quantity double,
    resourceid varchar,
    resourcelocation varchar,
    servicename varchar,
    subscriptionguid varchar,
    subscriptionid varchar,
    subscriptionname varchar,
    tags varchar,
    unitofmeasure varchar,
    source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month', 'day'])
;

DELETE FROM hive.{{schema | sqlsafe}}.managed_azure_uuid_temp
WHERE source = {{cloud_provider_uuid}}
    AND year = {{year}}
    AND month= {{month}};

INSERT INTO hive.{{schema | sqlsafe}}.managed_azure_uuid_temp (
    row_uuid,
    additionalinfo,
    billingcurrency,
    billingcurrencycode,
    consumedservice,
    costinbillingcurrency,
    date,
    metercategory,
    metername,
    quantity,
    resourceid,
    resourcelocation,
    servicename,
    subscriptionguid,
    subscriptionid,
    subscriptionname,
    tags,
    unitofmeasure,
    source,
    year,
    month,
    day
)
SELECT
    cast(uuid() as varchar) as row_uuid,
    azure.additionalinfo,
    azure.billingcurrency,
    azure.billingcurrencycode,
    azure.consumedservice,
    azure.costinbillingcurrency,
    azure.date,
    azure.metercategory,
    azure.metername,
    azure.quantity,
    azure.resourceid,
    azure.resourcelocation,
    azure.servicename,
    azure.subscriptionguid,
    azure.subscriptionid,
    azure.subscriptionname,
    azure.tags,
    azure.unitofmeasure,
    azure.source as source,
    azure.year,
    azure.month,
    cast(day(azure.date) as varchar) as day
FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
WHERE azure.source = {{cloud_provider_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND azure.date >= {{start_date}}
    AND azure.date < date_add('day', 1, {{end_date}});

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp
(
    row_uuid varchar, -- custom
    usage_start timestamp, -- custom
    resource_id varchar, -- custom
    service_name varchar, -- custom
    data_transfer_direction varchar, -- custom
    instance_type varchar, -- custom
    subscription_guid varchar, -- custom
    subscription_name varchar, -- custom
    resource_location varchar, -- custom
    unit_of_measure varchar, -- custom
    usage_quantity double, -- custom
    currency varchar, -- custom
    pretax_cost double, -- custom
    date timestamp(3),
    metername varchar,
    complete_resource_id varchar,
    tags varchar,
    resource_id_matched boolean,
    matched_tag varchar,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;

-- TODO: we may need a managed version of this table
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp
(
    resource_id varchar,
    capacity integer,
    usage_start timestamp,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp
(
    row_uuid varchar,
    cluster_id varchar,
    cluster_alias varchar,
    data_source varchar,
    namespace varchar,
    node varchar,
    persistentvolumeclaim varchar,
    persistentvolume varchar,
    storageclass varchar,
    resource_id varchar,
    usage_start timestamp,
    usage_end timestamp,
    service_name varchar,
    data_transfer_direction varchar,
    instance_type varchar,
    subscription_guid varchar,
    subscription_name varchar,
    resource_location varchar,
    unit_of_measure varchar,
    usage_quantity double,
    currency varchar,
    pretax_cost double,
    markup_cost double,
    pod_cost double,
    project_markup_cost double,
    pod_usage_cpu_core_hours double,
    pod_request_cpu_core_hours double,
    pod_effective_usage_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    pod_effective_usage_memory_gigabyte_hours double,
    node_capacity_cpu_core_hours double,
    node_capacity_memory_gigabyte_hours double,
    cluster_capacity_cpu_core_hours double,
    cluster_capacity_memory_gigabyte_hours double,
    pod_labels varchar,
    volume_labels varchar,
    tags varchar,
    project_rank integer,
    data_source_rank integer,
    matched_tag varchar,
    resource_id_matched boolean,
    cost_category_id int,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary
(
    row_uuid varchar,
    cluster_id varchar,
    cluster_alias varchar,
    data_source varchar,
    namespace varchar,
    node varchar,
    persistentvolumeclaim varchar,
    persistentvolume varchar,
    storageclass varchar,
    resource_id varchar,
    usage_start timestamp,
    usage_end timestamp,
    service_name varchar,
    data_transfer_direction varchar,
    instance_type varchar,
    subscription_guid varchar,
    subscription_name varchar,
    resource_location varchar,
    unit_of_measure varchar,
    usage_quantity double,
    currency varchar,
    pretax_cost double,
    markup_cost double,
    pod_cost double,
    project_markup_cost double,
    pod_usage_cpu_core_hours double,
    pod_request_cpu_core_hours double,
    pod_effective_usage_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    pod_effective_usage_memory_gigabyte_hours double,
    node_capacity_cpu_core_hours double,
    node_capacity_memory_gigabyte_hours double,
    cluster_capacity_cpu_core_hours double,
    cluster_capacity_memory_gigabyte_hours double,
    pod_labels varchar,
    volume_labels varchar,
    tags varchar,
    project_rank integer,
    data_source_rank integer,
    matched_tag varchar,
    resource_id_matched boolean,
    cost_category_id int,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;
