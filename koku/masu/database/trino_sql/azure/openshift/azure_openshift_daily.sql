-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.azure_openshift_daily
(
    accountname varchar,
    accountownerid varchar,
    additionalinfo varchar,
    availabilityzone varchar,
    billingaccountid varchar,
    billingaccountname varchar,
    billingcurrency varchar,
    billingcurrencycode varchar,
    billingperiodenddate timestamp,
    billingperiodstartdate timestamp,
    billingprofileid varchar,
    billingprofilename varchar,
    chargetype varchar,
    consumedservice varchar,
    costcenter varchar,
    costinbillingcurrency double,
    currency varchar,
    date timestamp,
    effectiveprice double,
    frequency varchar,
    instanceid varchar,
    invoicesectionid varchar,
    invoicesectionname varchar,
    isazurecrediteligible varchar,
    metercategory varchar,
    meterid varchar,
    metername varchar,
    meterregion varchar,
    metersubcategory varchar,
    offerid varchar,
    partnumber varchar,
    paygprice double,
    planname varchar,
    pretaxcost double,
    pricingmodel varchar,
    productname varchar,
    productorderid varchar,
    productordername varchar,
    publishername varchar,
    publishertype varchar,
    quantity double,
    reservationid varchar,
    reservationname varchar,
    resourcegroup varchar,
    resourceid varchar,
    resourcelocation varchar,
    resourcename varchar,
    resourcerate double,
    resourcetype varchar,
    servicefamily varchar,
    serviceinfo1 varchar,
    serviceinfo2 varchar,
    servicename varchar,
    servicetier varchar,
    subscriptionguid varchar,
    subscriptionid varchar,
    subscriptionname varchar,
    tags varchar,
    term varchar,
    unitofmeasure varchar,
    unitprice double,
    usagedatetime timestamp,
    usagequantity double,
    resource_id_matched boolean,
    matched_tag varchar,
    azure_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['azure_source', 'ocp_source', 'year', 'month', 'day'])
;

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.azure_openshift_daily (
    accountname,
    accountownerid,
    additionalinfo,
    availabilityzone,
    billingaccountid,
    billingaccountname,
    billingcurrency,
    billingcurrencycode,
    billingperiodenddate,
    billingperiodstartdate,
    billingprofileid,
    billingprofilename,
    chargetype,
    consumedservice,
    costcenter,
    costinbillingcurrency,
    currency,
    date,
    effectiveprice,
    frequency,
    instanceid,
    invoicesectionid,
    invoicesectionname,
    isazurecrediteligible,
    metercategory,
    meterid,
    metername,
    meterregion,
    metersubcategory,
    offerid,
    partnumber,
    paygprice,
    planname,
    pretaxcost,
    pricingmodel,
    productname,
    productorderid,
    productordername,
    publishername,
    publishertype,
    quantity,
    reservationid,
    reservationname,
    resourcegroup,
    resourceid,
    resourcelocation,
    resourcename,
    resourcerate,
    resourcetype,
    servicefamily,
    serviceinfo1,
    serviceinfo2,
    servicename,
    servicetier,
    subscriptionguid,
    subscriptionid,
    subscriptionname,
    tags,
    term,
    unitofmeasure,
    unitprice,
    usagedatetime,
    usagequantity,
    resource_id_matched,
    matched_tag,
    azure_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_azure_resource_names AS (
    SELECT DISTINCT coalesce(azure.resourceid, azure.instanceid) as resource_name
    FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
    WHERE source = {{azure_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND coalesce(azure.date, azure.usagedatetime) >= {{start_date}}
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
    SELECT resource_names.resource_name
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON strpos(resource_names.resource_name, nodes.node) != 0

    UNION

    SELECT resource_names.resource_name
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON strpos(resource_names.resource_name, volumes.persistentvolume) != 0
),
cte_tag_matches AS (
  SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)

  UNION

  SELECT * FROM unnest(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']) as t(matched_tag)
)
SELECT
    azure.accountname,
    azure.accountownerid,
    azure.additionalinfo,
    azure.availabilityzone,
    azure.billingaccountid,
    azure.billingaccountname,
    azure.billingcurrency,
    azure.billingcurrencycode,
    azure.billingperiodenddate,
    azure.billingperiodstartdate,
    azure.billingprofileid,
    azure.billingprofilename,
    azure.chargetype,
    azure.consumedservice,
    azure.costcenter,
    azure.costinbillingcurrency,
    azure.currency,
    azure.date,
    azure.effectiveprice,
    azure.frequency,
    azure.instanceid,
    azure.invoicesectionid,
    azure.invoicesectionname,
    azure.isazurecrediteligible,
    azure.metercategory,
    azure.meterid,
    azure.metername,
    azure.meterregion,
    azure.metersubcategory,
    azure.offerid,
    azure.partnumber,
    azure.paygprice,
    azure.planname,
    azure.pretaxcost,
    azure.pricingmodel,
    azure.productname,
    azure.productorderid,
    azure.productordername,
    azure.publishername,
    azure.publishertype,
    azure.quantity,
    azure.reservationid,
    azure.reservationname,
    azure.resourcegroup,
    azure.resourceid,
    azure.resourcelocation,
    azure.resourcename,
    azure.resourcerate,
    azure.resourcetype,
    azure.servicefamily,
    azure.serviceinfo1,
    azure.serviceinfo2,
    azure.servicename,
    azure.servicetier,
    azure.subscriptionguid,
    azure.subscriptionid,
    azure.subscriptionname,
    azure.tags,
    azure.term,
    azure.unitofmeasure,
    azure.unitprice,
    azure.usagedatetime,
    azure.usagequantity,
    CASE WHEN resource_names.resource_name IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    tag_matches.matched_tag as matched_tag,
    azure.source as azure_source,
    {{ocp_source_uuid}} as ocp_source,
    azure.year,
    azure.month,
    cast(day(coalesce(azure.date, azure.usagedatetime)) as varchar) as day
FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON coalesce(azure.resourceid, azure.instanceid) = resource_names.resource_name
LEFT JOIN cte_tag_matches AS tag_matches
    ON strpos(azure.tags, tag_matches.matched_tag) != 0
WHERE azure.source = {{azure_source_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND coalesce(azure.date, azure.usagedatetime) >= {{start_date}}
    AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, {{end_date}})
    AND (resource_names.resource_name IS NOT NULL OR tag_matches.matched_tag IS NOT NULL)
