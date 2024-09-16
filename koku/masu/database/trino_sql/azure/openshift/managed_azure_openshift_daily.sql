-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_openshift_daily
(
    accountname varchar,
    accountownerid varchar,
    additionalinfo varchar,
    availabilityzone varchar,
    billingaccountid varchar,
    billingaccountname varchar,
    billingcurrency varchar,
    billingcurrencycode varchar,
    billingperiodenddate timestamp(3),
    billingperiodstartdate timestamp(3),
    billingprofileid varchar,
    billingprofilename varchar,
    chargetype varchar,
    consumedservice varchar,
    costcenter varchar,
    costinbillingcurrency double,
    date timestamp(3),
    effectiveprice double,
    frequency varchar,
    invoiceid varchar,
    invoicesectionid varchar,
    isazurecrediteligible varchar,
    metercategory varchar,
    meterid varchar,
    metername varchar,
    meterregion varchar,
    metersubcategory varchar,
    offerid varchar,
    partnumber varchar,
    planname varchar,
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
    resource_id_matched boolean,
    matched_tag varchar,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_azure_openshift_daily (
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
    date,
    effectiveprice,
    frequency,
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
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_azure_resource_names AS (
    SELECT DISTINCT resourceid, servicefamily
    FROM hive.{{schema | sqlsafe}}.azure_line_items
    WHERE source = {{azure_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND date >= {{start_date}}
        AND date < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
    SELECT resource_names.resourceid, resource_names.servicefamily
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON strpos(resource_names.resourceid, nodes.node) != 0

    UNION

    SELECT resource_names.resourceid, resource_names.servicefamily
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON (
            strpos(resource_names.resourceid, volumes.persistentvolume) != 0
            OR strpos(resource_names.resourceid, volumes.csi_volume_handle) != 0
        )

),
cte_tag_matches AS (
  SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)

  UNION

  SELECT * FROM unnest(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']) as t(matched_tag)
),
cte_agg_tags AS (
    SELECT array_agg(matched_tag) as matched_tags from cte_tag_matches
)
SELECT azure.accountname,
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
    azure.date,
    azure.effectiveprice,
    azure.frequency,
    azure.invoiceid,
    azure.invoicesectionid,
    azure.isazurecrediteligible,
    azure.metercategory,
    azure.meterid,
    azure.metername,
    azure.meterregion,
    azure.metersubcategory,
    azure.offerid,
    azure.partnumber,
    azure.planname,
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
    CASE WHEN resource_names.resourceid IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(tags, x ) != 0), ',') as matched_tag,
    azure.source as source,
    {{ocp_source_uuid}} as ocp_source,
    azure.year,
    azure.month,
    cast(day(azure.date) as varchar) as day
FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON substr(azure.resourceid, -length(resource_names.resourceid)) = resource_names.resourceid
    AND azure.servicefamily = resource_names.servicefamily
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(tags, x) != 0)
    AND resource_names.resourceid IS NULL
WHERE azure.source = {{azure_source_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND azure.date >= {{start_date}}
    AND azure.date < date_add('day', 1, {{end_date}})
    AND (resource_names.resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL)
