-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_openshift_daily
(
    invoicesectionname varchar,
    accountname varchar,
    accountownerid varchar,
    subscriptionguid varchar,
    subscriptionname varchar,
    resourcegroup varchar,
    resourcelocation varchar,
    date timestamp(3),
    metercategory varchar,
    metersubcategory varchar,
    meterid varchar,
    metername varchar,
    meterregion varchar,
    unitofmeasure varchar,
    quantity double,
    effectiveprice double,
    costinbillingcurrency double,
    costcenter varchar,
    consumedservice varchar,
    tags varchar,
    offerid varchar,
    additionalinfo varchar,
    serviceinfo1 varchar,
    serviceinfo2 varchar,
    resourcename varchar,
    reservationid varchar,
    reservationname varchar,
    unitprice double,
    productorderid varchar,
    productordername varchar,
    term varchar,
    publishertype varchar,
    publishername varchar,
    chargetype varchar,
    frequency varchar,
    pricingmodel varchar,
    availabilityzone varchar,
    billingaccountid varchar,
    billingcurrencycode varchar,
    billingaccountname varchar,
    billingperiodstartdate timestamp(3),
    billingperiodenddate timestamp(3),
    billingprofileid varchar,
    billingprofilename varchar,
    resourceid varchar,
    invoicesectionid varchar,
    isazurecrediteligible varchar,
    partnumber varchar,
    marketprice varchar,
    planname varchar,
    servicefamily varchar,
    invoiceid varchar,
    previousinvoiceid varchar,
    resellername varchar,
    resellermpnid varchar,
    serviceperiodenddate varchar,
    serviceperiodstartdate varchar,
    productname varchar,
    productid varchar,
    publisherid varchar,
    location varchar,
    pricingcurrencycode varchar,
    costinpricingcurrency varchar,
    costinusd varchar,
    paygcostinbillingcurrency varchar,
    paygcostinusd varchar,
    exchangerate varchar,
    exchangeratedate varchar,
    billingcurrency varchar,
    servicename varchar,
    resourcetype varchar,
    subscriptionid varchar,
    servicetier varchar,
    paygprice double,
    resourcerate double,
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
    invoicesectionname,
    accountname,
    accountownerid,
    subscriptionguid,
    subscriptionname,
    resourcegroup,
    resourcelocation,
    date,
    metercategory,
    metersubcategory,
    meterid,
    metername,
    meterregion,
    unitofmeasure,
    quantity,
    effectiveprice,
    costinbillingcurrency,
    costcenter,
    consumedservice,
    tags,
    offerid,
    additionalinfo,
    serviceinfo1,
    serviceinfo2,
    resourcename,
    reservationid,
    reservationname,
    unitprice,
    productorderid,
    productordername,
    term,
    publishertype,
    publishername,
    chargetype,
    frequency,
    pricingmodel,
    availabilityzone,
    billingaccountid,
    billingcurrencycode,
    billingaccountname,
    billingperiodstartdate,
    billingperiodenddate,
    billingprofileid,
    billingprofilename,
    resourceid,
    invoicesectionid,
    isazurecrediteligible,
    partnumber,
    marketprice,
    planname,
    servicefamily,
    invoiceid,
    previousinvoiceid,
    resellername,
    resellermpnid,
    serviceperiodenddate,
    serviceperiodstartdate,
    productname,
    productid,
    publisherid,
    location,
    pricingcurrencycode,
    costinpricingcurrency,
    costinusd,
    paygcostinbillingcurrency,
    paygcostinusd,
    exchangerate,
    exchangeratedate,
    billingcurrency,
    servicename,
    resourcetype,
    subscriptionid,
    servicetier,
    paygprice,
    resourcerate,
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
SELECT azure.invoicesectionname,
    azure.accountname,
    azure.accountownerid,
    azure.subscriptionguid,
    azure.subscriptionname,
    azure.resourcegroup,
    azure.resourcelocation,
    azure.date,
    azure.metercategory,
    azure.metersubcategory,
    azure.meterid,
    azure.metername,
    azure.meterregion,
    azure.unitofmeasure,
    azure.quantity,
    azure.effectiveprice,
    azure.costinbillingcurrency,
    azure.costcenter,
    azure.consumedservice,
    azure.tags,
    azure.offerid,
    azure.additionalinfo,
    azure.serviceinfo1,
    azure.serviceinfo2,
    azure.resourcename,
    azure.reservationid,
    azure.reservationname,
    azure.unitprice,
    azure.productorderid,
    azure.productordername,
    azure.term,
    azure.publishertype,
    azure.publishername,
    azure.chargetype,
    azure.frequency,
    azure.pricingmodel,
    azure.availabilityzone,
    azure.billingaccountid,
    azure.billingcurrencycode,
    azure.billingaccountname,
    azure.billingperiodstartdate,
    azure.billingperiodenddate,
    azure.billingprofileid,
    azure.billingprofilename,
    azure.resourceid,
    azure.invoicesectionid,
    azure.isazurecrediteligible,
    azure.partnumber,
    azure.marketprice,
    azure.planname,
    azure.servicefamily,
    azure.invoiceid,
    azure.previousinvoiceid,
    azure.resellername,
    azure.resellermpnid,
    azure.serviceperiodenddate,
    azure.serviceperiodstartdate,
    azure.productname,
    azure.productid,
    azure.publisherid,
    azure.location,
    azure.pricingcurrencycode,
    azure.costinpricingcurrency,
    azure.costinusd,
    azure.paygcostinbillingcurrency,
    azure.paygcostinusd,
    azure.exchangerate,
    azure.exchangeratedate,
    azure.billingcurrency,
    azure.servicename,
    azure.resourcetype,
    azure.subscriptionid,
    azure.servicetier,
    azure.paygprice,
    azure.resourcerate,
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
WHERE azure.source = {{azure_source_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND azure.date >= {{start_date}}
    AND azure.date < date_add('day', 1, {{end_date}})
    AND (resource_names.resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL)
