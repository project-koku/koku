DELETE FROM hive.{{schema | sqlsafe}}.managed_aws_openshift_daily_temp
WHERE source = {{cloud_provider_uuid}}
AND ocp_source = {{ocp_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

INSERT INTO hive.{{schema | sqlsafe}}.managed_aws_openshift_daily_temp (
    row_uuid,
    resource_id,
    product_code,
    usage_start,
    usage_account_id,
    availability_zone,
    product_family,
    instance_type,
    region,
    unit,
    tags,
    aws_cost_category,
    usage_amount,
    data_transfer_direction,
    currency_code,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    calculated_amortized_cost,
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
    WHERE source = {{cloud_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND lineitem_usagestartdate >= {{start_date}}
        AND lineitem_usagestartdate < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT resource_id
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND resource_id != ''
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND persistentvolume != ''
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
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
),
cte_enabled_tag_keys AS (
    SELECT
    CASE WHEN array_agg(key) IS NOT NULL
        THEN array_union(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project'], array_agg(key))
        ELSE ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']
    END as enabled_keys
    FROM postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
    WHERE enabled = TRUE
    AND provider_type = 'AWS'
)
SELECT
    aws.row_uuid,
    nullif(aws.lineitem_resourceid, '') as resource_id,
    CASE
        WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
        ELSE nullif(aws.lineitem_productcode, '')
    END as product_code,
    aws.lineitem_usagestartdate as usage_start,
    aws.lineitem_usageaccountid as usage_account_id,
    nullif(aws.lineitem_availabilityzone, '') as availability_zone,
    nullif(aws.product_productfamily, '') as product_family,
    nullif(aws.product_instancetype, '') as instance_type,
    nullif(aws.product_region, '') as region,
    nullif(aws.pricing_unit, '') as unit,
    json_format(
        cast(
            map_filter(
                cast(json_parse(aws.resourcetags) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as tags,
    aws.costcategory as aws_cost_category,
    aws.lineitem_usageamount as usage_amount,
    CASE
        -- Is this a network record?
        WHEN aws.lineitem_productcode = 'AmazonEC2' AND aws.product_productfamily = 'Data Transfer' THEN
            -- Yes, it's a network record. What's the direction?
            CASE
                WHEN strpos(lower(aws.lineitem_usagetype), 'in-bytes') > 0 THEN 'IN'
                WHEN strpos(lower(aws.lineitem_usagetype), 'out-bytes') > 0 THEN 'OUT'
                WHEN (strpos(lower(aws.lineitem_usagetype), 'regional-bytes') > 0 AND strpos(lower(lineitem_operation), '-in') > 0) THEN 'IN'
                WHEN (strpos(lower(aws.lineitem_usagetype), 'regional-bytes') > 0 AND strpos(lower(lineitem_operation), '-out') > 0) THEN 'OUT'
                ELSE NULL
            END
    END AS data_transfer_direction,
    nullif(aws.lineitem_currencycode, '') as currency_code,
    -- SavingsPlanCoveredUsage needs to be negated to show accurate cost COST-5098
    CASE
        WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
        THEN 0.0
        ELSE aws.lineitem_unblendedcost
    END as unblended_cost,
    CASE
        WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
        THEN 0.0
        ELSE aws.lineitem_blendedcost
    END as blended_cost,
    aws.savingsplan_savingsplaneffectivecost as savingsplan_effective_cost,
    CASE
        WHEN aws.lineitem_lineitemtype='Tax'
        OR   aws.lineitem_lineitemtype='Usage'
        THEN aws.lineitem_unblendedcost
        ELSE aws.savingsplan_savingsplaneffectivecost
    END as calculated_amortized_cost,
    CASE WHEN resource_names.lineitem_resourceid IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(resourcetags, x ) != 0), ',') as matched_tag,
    aws.source as source,
    {{ocp_provider_uuid}} as ocp_source,
    aws.year,
    aws.month,
    cast(day(aws.lineitem_usagestartdate) as varchar) as day
FROM hive.{{schema | sqlsafe}}.aws_line_items_daily AS aws
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON resource_names.lineitem_resourceid = aws.lineitem_resourceid
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(resourcetags, x) != 0)
    AND resource_names.lineitem_resourceid IS NULL
CROSS JOIN cte_enabled_tag_keys as etk
WHERE aws.source = {{cloud_provider_uuid}}
    AND aws.year = {{year}}
    AND aws.month= {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (resource_names.lineitem_resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL)
