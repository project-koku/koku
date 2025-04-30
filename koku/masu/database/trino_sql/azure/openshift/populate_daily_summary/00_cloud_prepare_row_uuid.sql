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
