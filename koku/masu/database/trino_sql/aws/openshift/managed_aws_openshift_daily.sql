-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_aws_openshift_daily
(
    lineitem_resourceid varchar,
    lineitem_usagestartdate timestamp(3),
    bill_payeraccountid varchar,
    lineitem_usageaccountid varchar,
    lineitem_legalentity varchar,
    lineitem_lineitemdescription varchar,
    bill_billingentity varchar,
    lineitem_productcode varchar,
    lineitem_availabilityzone varchar,
    lineitem_lineitemtype varchar,
    lineitem_usagetype varchar,
    lineitem_operation varchar,
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
    bill_invoiceid varchar,
    product_productname varchar,
    product_vcpu varchar,
    product_memory varchar,
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
INSERT INTO hive.{{schema | sqlsafe}}.managed_aws_openshift_daily (
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
    source,
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
        AND resource_id != ''
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND persistentvolume != ''
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
    -- this matches the endswith method done with resource id matching python
    SELECT resource_names.lineitem_resourceid
    FROM cte_aws_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON substr(resource_names.lineitem_resourceid, -length(nodes.resource_id)) = nodes.resource_id

    UNION

    SELECT resource_names.lineitem_resourceid
    FROM cte_aws_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON (
            substr(resource_names.lineitem_resourceid, -length(volumes.persistentvolume)) = volumes.persistentvolume
            OR (volumes.csi_volume_handle != '' AND substr(resource_names.lineitem_resourceid, -length(volumes.csi_volume_handle)) = volumes.csi_volume_handle)
        )

),
cte_agg_tags AS (
    SELECT array_agg(cte_tag_matches.matched_tag) as matched_tags from (
        SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)
    ) as cte_tag_matches
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
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(resourcetags, x ) != 0), ',') as matched_tag,
    aws.source as source,
    {{ocp_source_uuid}} as ocp_source,
    aws.year,
    aws.month,
    cast(day(aws.lineitem_usagestartdate) as varchar) as day
FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON resource_names.lineitem_resourceid = aws.lineitem_resourceid
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(resourcetags, x) != 0)
    AND resource_names.lineitem_resourceid IS NULL
WHERE aws.source = {{aws_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month= {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (resource_names.lineitem_resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL)
