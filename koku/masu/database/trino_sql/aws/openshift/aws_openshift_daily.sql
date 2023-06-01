lineitem_resourceid varchar,
lineitem_usagestartdate timestamp,
bill_payeraccountid varchar,
lineitem_usageaccountid varchar,
lineitem_legalentity varchar,
lineitem_lineitemdescription varchar,
bill_billingentity varchar,
lineitem_productcode varchar,
lineitem_availabilityzone varchar,
lineitem_lineitemtype varchar,
product_productfamily varchar,
product_instancetype varchar,
product_region varchar,
pricing_unit varchar,
resourcetags varchar,
costcategory varchar,
lineitem_usageamount double,
lineitem_normalizationfactor double,
lineitem_normalizedusageamount double,
lineitem_currencycode varchar,
lineitem_unblendedrate double,
lineitem_unblendedcost double,
lineitem_blendedrate double,
lineitem_blendedcost double,
pricing_publicondemandcost double,
pricing_publicondemandrate double,
savingsplan_savingsplaneffectivecost double,
product_productname varchar,
bill_invoiceid varchar,
resource_id_matched boolean,
matched_tag varchar,
uuid varchar,
aws_source varchar,
ocp_source varchar,
year varchar,
month varchar
day varchar
-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.aws_openshift_daily
(
    lineitem_resourceid varchar,
    lineitem_usagestartdate timestamp,
    bill_payeraccountid varchar,
    lineitem_usageaccountid varchar,
    lineitem_legalentity varchar,
    lineitem_lineitemdescription varchar,
    bill_billingentity varchar,
    lineitem_productcode varchar,
    lineitem_availabilityzone varchar,
    lineitem_lineitemtype varchar,
    product_productfamily varchar,
    product_instancetype varchar,
    product_region varchar,
    pricing_unit varchar,
    resourcetags varchar,
    costcategory varchar,
    lineitem_usageamount double,
    lineitem_normalizationfactor double,
    lineitem_normalizedusageamount double,
    lineitem_currencycode varchar,
    lineitem_unblendedrate double,
    lineitem_unblendedcost double,
    lineitem_blendedrate double,
    lineitem_blendedcost double,
    pricing_publicondemandcost double,
    pricing_publicondemandrate double,
    savingsplan_savingsplaneffectivecost double,
    product_productname varchar,
    bill_invoiceid varchar,
    resource_id_matched boolean,
    matched_tag varchar,
    uuid varchar,
    aws_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['aws_source', 'ocp_source', 'year', 'month', 'day'])
;

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.aws_openshift_daily (
    lineitem_resourceid,
    lineitem_usagestartdate,
    bill_payeraccountid,
    lineitem_usageaccountid,
    lineitem_legalentity,
    lineitem_lineitemdescription,
    bill_billingentity,
    lineitem_productcode,
    lineitem_availabilityzone,
    lineitem_lineitemtype,
    product_productfamily,
    product_instancetype,
    product_region,
    pricing_unit,
    resourcetags,
    costcategory,
    lineitem_usageamount,
    lineitem_normalizationfactor,
    lineitem_normalizedusageamount,
    lineitem_currencycode,
    lineitem_unblendedrate,
    lineitem_unblendedcost,
    lineitem_blendedrate,
    lineitem_blendedcost,
    pricing_publicondemandcost,
    pricing_publicondemandrate,
    savingsplan_savingsplaneffectivecost,
    product_productname,
    bill_invoiceid,
    resource_id_matched,
    matched_tag,
    uuid,
    aws_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_aws_resource_names AS (
    SELECT DISTINCT lineitem_resourceid
    FROM hive.{{schema | sqlsafe}}.aws_line_items_daily
    WHERE source = {{aws_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND lineitem_usagestartdate >= {{start_date}}
        AND lineitem_usagestartdate < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT resource_id
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
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
    SELECT resource_names.lineitem_resourceid
    FROM cte_aws_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON strpos(resource_names.lineitem_resourceid, nodes.resource_id) != 0

    UNION

    SELECT resource_names.lineitem_resourceid
    FROM cte_aws_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON strpos(resource_names.lineitem_resourceid, volumes.persistentvolume) != 0
),
cte_tag_matches AS (
  SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)

  UNION

  SELECT * FROM unnest(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']) as t(matched_tag)
)
SELECT aws.lineitem_resourceid,
    aws.lineitem_usagestartdate,
    aws.bill_payeraccountid,
    aws.lineitem_usageaccountid,
    aws.lineitem_legalentity,
    aws.lineitem_lineitemdescription,
    aws.bill_billingentity,
    aws.lineitem_productcode,
    aws.lineitem_availabilityzone,
    aws.lineitem_lineitemtype,
    aws.product_productfamily,
    aws.product_instancetype,
    aws.product_region,
    aws.pricing_unit,
    aws.resourcetags,
    aws.costcategory,
    aws.lineitem_usageamount,
    aws.lineitem_normalizationfactor,
    aws.lineitem_normalizedusageamount,
    aws.lineitem_currencycode,
    aws.lineitem_unblendedrate,
    aws.lineitem_unblendedcost,
    aws.lineitem_blendedrate,
    aws.lineitem_blendedcost,
    aws.pricing_publicondemandcost,
    aws.pricing_publicondemandrate,
    aws.savingsplan_savingsplaneffectivecost,
    aws.product_productname,
    aws.bill_invoiceid,
    CASE WHEN resource_names.lineitem_resourceid IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    tag_matches.matched_tag as matched_tag,
    aws.source as aws_source,
    {{ocp_source_uuid}} as ocp_source,
    aws.year,
    aws.month,
    cast(day(aws.lineitem_usagestartdate) as varchar) as day
FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON aws.lineitem_resourceid = resource_names.lineitem_resourceid
LEFT JOIN cte_tag_matches AS tag_matches
    ON strpos(aws.resourcetags, tag_matches.matched_tag) != 0
WHERE aws.source = {{aws_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month= {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (resource_names.lineitem_resourceid IS NOT NULL OR tag_matches.matched_tag IS NOT NULL)
