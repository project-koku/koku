-- First we'll store the data in a "temp" table to do our grouping against
CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp
(
    uuid varchar,
    usage_start timestamp,
    resource_id varchar,
    product_code varchar,
    product_family varchar,
    instance_type varchar,
    usage_account_id varchar,
    availability_zone varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    data_transfer_direction varchar,
    currency_code varchar,
    unblended_cost double,
    blended_cost double,
    savingsplan_effective_cost double,
    calculated_amortized_cost double,
    tags varchar,
    aws_cost_category varchar,
    resource_id_matched boolean,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.aws_openshift_daily_tag_matched_temp
(
    uuid varchar,
    usage_start timestamp,
    resource_id varchar,
    product_code varchar,
    product_family varchar,
    instance_type varchar,
    usage_account_id varchar,
    availability_zone varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency_code varchar,
    unblended_cost double,
    blended_cost double,
    savingsplan_effective_cost double,
    calculated_amortized_cost double,
    tags varchar,
    aws_cost_category varchar,
    matched_tag varchar,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp
(
    aws_uuid varchar,
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
    product_code varchar,
    product_family varchar,
    instance_type varchar,
    usage_account_id varchar,
    availability_zone varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency_code varchar,
    unblended_cost double,
    markup_cost double,
    blended_cost double,
    markup_cost_blended double,
    savingsplan_effective_cost double,
    markup_cost_savingsplan double,
    calculated_amortized_cost double,
    markup_cost_amortized double,
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
    aws_cost_category varchar, -- AWS Cost category
    cost_category_id int, -- Internal OpenShift category ID
    project_rank integer,
    data_source_rank integer,
    resource_id_matched boolean,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary
(
    aws_uuid varchar,
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
    product_code varchar,
    product_family varchar,
    instance_type varchar,
    usage_account_id varchar,
    account_alias_id integer,
    availability_zone varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    data_transfer_direction varchar,
    currency_code varchar,
    unblended_cost double,
    markup_cost double,
    blended_cost double,
    markup_cost_blended double,
    savingsplan_effective_cost double,
    markup_cost_savingsplan double,
    calculated_amortized_cost double,
    markup_cost_amortized double,
    pod_cost double,
    project_markup_cost double,
    pod_labels varchar,
    tags varchar,
    aws_cost_category varchar, -- AWS Cost category
    cost_category_id int, -- Internal OpenShift category ID
    project_rank integer,
    data_source_rank integer,
    aws_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['aws_source', 'ocp_source', 'year', 'month', 'day'])
;

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.aws_openshift_disk_capacities_temp
(
    resource_id varchar,
    capacity integer,
    usage_start timestamp,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month']);

INSERT INTO hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp (
    uuid,
    usage_start,
    resource_id,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    data_transfer_direction,
    currency_code,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    calculated_amortized_cost,
    tags,
    aws_cost_category,
    resource_id_matched,
    ocp_source,
    year,
    month
)
SELECT cast(uuid() as varchar) as uuid,
    aws.lineitem_usagestartdate as usage_start,
    nullif(aws.lineitem_resourceid, '') as resource_id,
    CASE
        WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
        ELSE nullif(aws.lineitem_productcode, '')
    END as product_code,
    nullif(aws.product_productfamily, '') as product_family,
    nullif(aws.product_instancetype, '') as instance_type,
    max(aws.lineitem_usageaccountid) as usage_account_id,
    nullif(aws.lineitem_availabilityzone, '') as availability_zone,
    nullif(aws.product_region, '') as region,
    max(nullif(aws.pricing_unit, '')) as unit,
    sum(aws.lineitem_usageamount) as usage_amount,
    -- Determine network direction
    CASE
        -- Is this a network record?
        WHEN max(aws.lineitem_productcode) = 'AmazonEC2' AND max(aws.product_productfamily) = 'Data Transfer' THEN
            -- Yes, it's a network record. What's the direction?
            CASE
                WHEN strpos(lower(max(aws.lineitem_usagetype)), 'in-bytes') > 0 THEN 'IN'
                WHEN strpos(lower(max(aws.lineitem_usagetype)), 'out-bytes') > 0 THEN 'OUT'
                WHEN (strpos(lower(max(aws.lineitem_usagetype)), 'regional-bytes') > 0 AND strpos(lower(max(lineitem_operation)), '-in') > 0) THEN 'IN'
                WHEN (strpos(lower(max(aws.lineitem_usagetype)), 'regional-bytes') > 0 AND strpos(lower(max(lineitem_operation)), '-out') > 0) THEN 'OUT'
                ELSE NULL
            END
    END AS data_transfer_direction,
    max(nullif(aws.lineitem_currencycode, '')) as currency_code,
    -- SavingsPlanCoveredUsage needs to be negated to show accurate cost COST-5098
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_unblendedcost
        END
        ) as unblended_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_blendedcost
        END
        ) as blended_cost,
    sum(aws.savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='Tax'
            OR   aws.lineitem_lineitemtype='Usage'
            THEN aws.lineitem_unblendedcost
            ELSE aws.savingsplan_savingsplaneffectivecost
        END
    ) as calculated_amortized_cost,
    aws.resourcetags as tags,
    aws.costcategory as aws_cost_category,
    max(aws.resource_id_matched) as resource_id_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(aws.year) as year,
    max(aws.month) as month
FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
WHERE aws.source = {{aws_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (aws.lineitem_resourceid IS NOT NULL AND aws.lineitem_resourceid != '')
    AND aws.resource_id_matched = TRUE
GROUP BY aws.lineitem_usagestartdate,
    aws.lineitem_resourceid,
    4, -- product_code
    aws.product_productfamily,
    aws.product_instancetype,
    aws.lineitem_availabilityzone,
    aws.product_region,
    aws.lineitem_usagetype,
    aws.resourcetags,
    aws.costcategory,
    lineitem_operation
;

INSERT INTO hive.{{schema | sqlsafe}}.aws_openshift_daily_tag_matched_temp (
    uuid,
    usage_start,
    resource_id,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    calculated_amortized_cost,
    tags,
    aws_cost_category,
    matched_tag,
    ocp_source,
    year,
    month
)
WITH cte_enabled_tag_keys AS (
    SELECT
    CASE WHEN array_agg(key) IS NOT NULL
        THEN array_union(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project'], array_agg(key))
        ELSE ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']
    END as enabled_keys
    FROM postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
    WHERE enabled = TRUE
    AND provider_type = 'AWS'
)
SELECT cast(uuid() as varchar) as uuid,
    aws.lineitem_usagestartdate as usage_start,
    nullif(aws.lineitem_resourceid, '') as resource_id,
    CASE
        WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
        ELSE nullif(aws.lineitem_productcode, '')
    END as product_code,
    nullif(aws.product_productfamily, '') as product_family,
    nullif(aws.product_instancetype, '') as instance_type,
    max(aws.lineitem_usageaccountid) as usage_account_id,
    nullif(aws.lineitem_availabilityzone, '') as availability_zone,
    nullif(aws.product_region, '') as region,
    max(nullif(aws.pricing_unit, '')) as unit,
    sum(aws.lineitem_usageamount) as usage_amount,
    max(nullif(aws.lineitem_currencycode, '')) as currency_code,
    -- SavingsPlanCoveredUsage needs to be negated to show accurate cost COST-5098
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_unblendedcost
        END
        ) as unblended_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_blendedcost
        END
        ) as blended_cost,
    sum(aws.savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='Tax'
            OR   aws.lineitem_lineitemtype='Usage'
            THEN aws.lineitem_unblendedcost
            ELSE aws.savingsplan_savingsplaneffectivecost
        END
    ) as calculated_amortized_cost,
    json_format(
        cast(
            map_filter(
                cast(json_parse(aws.resourcetags) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as tags,
    aws.costcategory as aws_cost_category,
    aws.matched_tag,
    {{ocp_source_uuid}} as ocp_source,
    max(aws.year) as year,
    max(aws.month) as month
FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
CROSS JOIN cte_enabled_tag_keys as etk
WHERE aws.source = {{aws_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (aws.lineitem_resourceid IS NOT NULL AND aws.lineitem_resourceid != '')
    AND (aws.resource_id_matched = FALSE OR aws.resource_id_matched IS NULL)
GROUP BY aws.lineitem_usagestartdate,
    aws.lineitem_resourceid,
    4, -- product_code
    aws.product_productfamily,
    aws.product_instancetype,
    aws.lineitem_availabilityzone,
    aws.product_region,
    aws.costcategory,
    17, -- tags
    aws.matched_tag
;

{% if unattributed_storage %}
-- Developer notes
-- We can't use the aws_openshift_daily table to calcualte the capacity
-- because it has already aggregated cost per each hour.
INSERT INTO hive.{{schema | sqlsafe}}.aws_openshift_disk_capacities_temp (
    resource_id,
    capacity,
    usage_start,
    ocp_source,
    year,
    month
)
WITH cte_hours as (
    SELECT DAY(last_day_of_month({{start_date}})) * 24 as in_month
),
cte_ocp_filtered_resources as (
    select
        distinct aws.resource_id as resource_id,
        {{ocp_source_uuid}} as ocp_source,
        DATE(aws.usage_start) as usage_start,
        aws.year as year,
        aws.month as month
    FROM hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp as aws
    JOIN hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON aws.usage_start = ocp.usage_start
        AND strpos(aws.resource_id, ocp.csi_volume_handle) != 0
        AND ocp.csi_volume_handle is not null
        AND ocp.csi_volume_handle != ''
    WHERE
        ocp.source_uuid = {{ocp_source_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}}
        AND aws.ocp_source = {{ocp_source_uuid}}
        AND aws.year = {{year}}
        AND aws.month = {{month}}
),
calculated_capacity AS (
    SELECT
        aws.lineitem_resourceid as resource_id,
        ROUND(MAX(aws.lineitem_unblendedcost) / (MAX(aws.lineitem_unblendedrate) / MAX(hours.in_month))) AS capacity,
        ocpaws.usage_start,
        {{ocp_source_uuid}} as ocp_source,
        {{year}} as year,
        {{month}} as month
    FROM hive.{{schema | sqlsafe}}.aws_line_items as aws
    INNER JOIN cte_ocp_filtered_resources as ocpaws
        ON aws.lineitem_resourceid = ocpaws.resource_id
        AND DATE(aws.lineitem_usagestartdate) = ocpaws.usage_start
    CROSS JOIN cte_hours as hours
    WHERE aws.year = {{year}}
    AND aws.month = {{month}}
    AND aws.source = {{aws_source_uuid}}
    GROUP BY aws.lineitem_resourceid, ocpaws.usage_start
)
SELECT *
FROM calculated_capacity
WHERE capacity > 0
{% endif %}
;


{% if not unattributed_storage %}
-- Maintain tag matching logic for disk resources
-- until unattributed storage is released
-- FIXME: Remove this section when the unleash flag is removed
INSERT INTO hive.{{schema | sqlsafe}}.aws_openshift_daily_tag_matched_temp (
    uuid,
    usage_start,
    resource_id,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    blended_cost,
    savingsplan_effective_cost,
    calculated_amortized_cost,
    tags,
    aws_cost_category,
    matched_tag,
    ocp_source,
    year,
    month
)
WITH cte_enabled_tag_keys AS (
    SELECT
    CASE WHEN array_agg(key) IS NOT NULL
        THEN array_union(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project'], array_agg(key))
        ELSE ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']
    END as enabled_keys
    FROM postgres.{{schema | sqlsafe}}.reporting_enabledtagkeys
    WHERE enabled = TRUE
    AND provider_type = 'AWS'
),
cte_csi_volume_handles as (
    SELECT distinct csi_volume_handle as csi_volume_handle
            FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as ocp
            WHERE ocp.source = {{ocp_source_uuid}}
                AND ocp.year = {{year}}
                AND ocp.month = {{month}}
)
SELECT cast(uuid() as varchar) as uuid,
    aws.lineitem_usagestartdate as usage_start,
    nullif(aws.lineitem_resourceid, '') as resource_id,
    CASE
        WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
        ELSE nullif(aws.lineitem_productcode, '')
    END as product_code,
    nullif(aws.product_productfamily, '') as product_family,
    nullif(aws.product_instancetype, '') as instance_type,
    max(aws.lineitem_usageaccountid) as usage_account_id,
    nullif(aws.lineitem_availabilityzone, '') as availability_zone,
    nullif(aws.product_region, '') as region,
    max(nullif(aws.pricing_unit, '')) as unit,
    sum(aws.lineitem_usageamount) as usage_amount,
    max(nullif(aws.lineitem_currencycode, '')) as currency_code,
    -- SavingsPlanCoveredUsage needs to be negated to show accurate cost COST-5098
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_unblendedcost
        END
        ) as unblended_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='SavingsPlanCoveredUsage'
            THEN 0.0
            ELSE aws.lineitem_blendedcost
        END
        ) as blended_cost,
    sum(aws.savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
    sum(
        CASE
            WHEN aws.lineitem_lineitemtype='Tax'
            OR   aws.lineitem_lineitemtype='Usage'
            THEN aws.lineitem_unblendedcost
            ELSE aws.savingsplan_savingsplaneffectivecost
        END
    ) as calculated_amortized_cost,
    json_format(
        cast(
            map_filter(
                cast(json_parse(aws.resourcetags) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as tags,
    aws.costcategory as aws_cost_category,
    aws.matched_tag,
    {{ocp_source_uuid}} as ocp_source,
    max(aws.year) as year,
    max(aws.month) as month
FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
CROSS JOIN cte_enabled_tag_keys as etk
CROSS JOIN cte_csi_volume_handles as csi
WHERE aws.source = {{aws_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    AND aws.lineitem_usagestartdate >= {{start_date}}
    AND aws.lineitem_usagestartdate < date_add('day', 1, {{end_date}})
    AND (aws.lineitem_resourceid IS NOT NULL AND aws.lineitem_resourceid != '')
    AND matched_tag != ''
    AND matched_tag is not null
    AND resource_id_matched = True
    AND strpos(aws.lineitem_resourceid, csi.csi_volume_handle) != 0
GROUP BY aws.lineitem_usagestartdate,
    aws.lineitem_resourceid,
    4, -- product_code
    aws.product_productfamily,
    aws.product_instancetype,
    aws.lineitem_availabilityzone,
    aws.product_region,
    aws.costcategory,
    17, -- tags
    aws.matched_tag
{% endif %}
;


{% if unattributed_storage %}
-- Storage disk resource id matching
-- Algorhtim:
-- (PV Capacity) / Disk Capacity * Cost of Disk
-- PV without PVCs are unattributed storage
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp (
    aws_uuid,
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
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
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
    volume_labels,
    tags,
    aws_cost_category,
    cost_category_id,
    resource_id_matched,
    ocp_source,
    year,
    month
)
SELECT  cast(uuid() as varchar) as aws_uuid, -- need a new uuid or it will deduplicate
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    'Storage' as data_source,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN 'Storage unattributed'
        ELSE max(ocp.namespace)
    END as namespace,
    max(ocp.node) as node,
    max(ocp.persistentvolumeclaim) as persistentvolumeclaim,
    max(ocp.persistentvolume) as persistentvolume,
    max(ocp.storageclass) as storageclass,
    max(aws.resource_id) as resource_id,
    max(aws.usage_start) as usage_start,
    max(aws.usage_start) as usage_end,
    max(aws.product_code) as product_code,
    max(aws.product_family) as product_family,
    max(aws.instance_type) as instance_type,
    max(aws.usage_account_id) as usage_account_id,
    max(aws.availability_zone) as availability_zone,
    max(aws.region) as region,
    max(aws.unit) as unit,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN cast(NULL as double)
        ELSE max(aws.usage_amount)
    END as usage_amount,
    max(aws.currency_code) as currency_code,
    max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.unblended_cost)  as unblended_cost,
    (max(persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.unblended_cost)) * cast({{markup}} as decimal(24,9)) as markup_cost,
    max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.blended_cost)  as blended_cost,
    (max(persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.blended_cost)) * cast({{markup}} as decimal(24,9)) as markup_cost_blended,
    max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.savingsplan_effective_cost)  as savingsplan_effective_cost,
    (max(persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.savingsplan_effective_cost)) * cast({{markup}} as decimal(24,9)) as markup_cost_savingsplan,
    max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.calculated_amortized_cost)  as calculated_amortized_cost,
    (max(persistentvolumeclaim_capacity_gigabyte) / max(aws_disk.capacity) * max(aws.calculated_amortized_cost)) * cast({{markup}} as decimal(24,9)) as markup_cost_amortized,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN cast(NULL as varchar)
        ELSE ocp.pod_labels
    END as pod_lables,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN cast(NULL as varchar)
        ELSE ocp.volume_labels
    END as volume_labels,
    max(aws.tags) as tags,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN NULL
        ELSE max(aws.aws_cost_category)
    END as aws_cost_category,
    CASE
        WHEN max(ocp.persistentvolumeclaim) = ''
            THEN NULL
        ELSE max(ocp.cost_category_id)
    END as cost_category_id,
    max(aws.resource_id_matched) as resource_id_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(aws.year) as year,
    max(aws.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp as aws
    ON aws.usage_start = ocp.usage_start
    AND strpos(aws.resource_id, ocp.csi_volume_handle) != 0
    AND ocp.csi_volume_handle is not null
    AND ocp.csi_volume_handle != ''
JOIN hive.{{schema | sqlsafe}}.aws_openshift_disk_capacities_temp AS aws_disk
    ON aws_disk.usage_start = aws.usage_start
    AND aws_disk.resource_id = aws.resource_id
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND ocp.persistentvolume is not null
    AND aws.ocp_source = {{ocp_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    -- Filter out Node Network Costs since they cannot be attributed to a namespace and are accounted for later
    AND aws.data_transfer_direction IS NULL
    AND ocp.namespace != 'Storage unattributed'
    AND aws.resource_id_matched = True
    AND aws_disk.year = {{year}}
    AND aws_disk.month = {{month}}
    AND aws_disk.ocp_source = {{ocp_source_uuid}}
GROUP BY aws.uuid, ocp.namespace, ocp.pod_labels, ocp.volume_labels
{% endif %}
;

{% if unattributed_storage %}
-- Unattributed Storage Cost:
-- ((Disk Capacity - Sum(PV capacity) / Disk Capacity) * Cost of Disk
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp (
    aws_uuid,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    usage_start,
    usage_end,
    product_code,
    product_family,
    instance_type,
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    calculated_amortized_cost,
    markup_cost_amortized,
    resource_id_matched,
    ocp_source,
    year,
    month
)
WITH cte_total_pv_capacity as (
    SELECT
        aws_resource_id,
        SUM(combined_requests.capacity) as total_pv_capacity,
        count(distinct cluster_id) as cluster_count
    FROM (
        SELECT
            ocp.persistentvolume,
            max(ocp.persistentvolumeclaim_capacity_gigabyte) as capacity,
            aws.resource_id as aws_resource_id,
            ocp.cluster_id
        FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp as aws
            ON (aws.usage_start = ocp.usage_start)
            AND strpos(aws.resource_id, ocp.csi_volume_handle) > 0
            AND ocp.csi_volume_handle is not null
            AND ocp.csi_volume_handle != ''
        WHERE ocp.year = {{year}}
            AND lpad(ocp.month, 2, '0') = {{month}}
            AND ocp.usage_start >= {{start_date}}
            AND ocp.usage_start < date_add('day', 1, {{end_date}})
            AND aws.ocp_source = {{ocp_source_uuid}}
            AND aws.year = {{year}}
            AND aws.month = {{month}}
        GROUP BY ocp.persistentvolume, aws.resource_id, ocp.cluster_id
    ) as combined_requests group by aws_resource_id
)
SELECT  cast(uuid() as varchar) as aws_uuid, -- need a new uuid or it will deduplicate
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    'Storage' as data_source,
    'Storage unattributed' as namespace,
    max(ocp.persistentvolumeclaim) as persistentvolumeclaim,
    max(ocp.persistentvolume) as persistentvolume,
    max(ocp.storageclass) as storageclass,
    max(aws.resource_id) as resource_id,
    max(aws.usage_start) as usage_start,
    max(aws.usage_start) as usage_end,
    max(aws.product_code) as product_code,
    max(aws.product_family) as product_family,
    max(aws.instance_type) as instance_type,
    max(aws.usage_account_id) as usage_account_id,
    max(aws.availability_zone) as availability_zone,
    max(aws.region) as region,
    max(aws.unit) as unit,
    cast(NULL as double) as usage_amount,
    max(aws.currency_code) as currency_code,
    (max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.unblended_cost) / max(pv_cap.cluster_count)  as unblended_cost,
    ((max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.unblended_cost)) * cast({{markup}} as decimal(24,9)) / max(pv_cap.cluster_count) as markup_cost,
    (max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.blended_cost) / max(pv_cap.cluster_count)  as blended_cost,
    ((max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.blended_cost)) * cast({{markup}} as decimal(24,9)) / max(pv_cap.cluster_count) as markup_cost_blended,
    (max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.savingsplan_effective_cost) / max(pv_cap.cluster_count)  as savingsplan_effective_cost,
    ((max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.savingsplan_effective_cost)) * cast({{markup}} as decimal(24,9)) / max(pv_cap.cluster_count) as markup_cost_savingsplan,
    (max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.calculated_amortized_cost) / max(pv_cap.cluster_count)  as calculated_amortized_cost,
    ((max(aws_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(aws_disk.capacity) * max(aws.calculated_amortized_cost)) * cast({{markup}} as decimal(24,9)) / max(pv_cap.cluster_count) as markup_cost_amortized,
    max(aws.resource_id_matched) as resource_id_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(aws.year) as year,
    max(aws.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp as aws
    ON aws.usage_start = ocp.usage_start
    AND strpos(aws.resource_id, ocp.csi_volume_handle) != 0
    AND ocp.csi_volume_handle is not null
    AND ocp.csi_volume_handle != ''
JOIN hive.{{schema | sqlsafe}}.aws_openshift_disk_capacities_temp AS aws_disk
    ON aws_disk.usage_start = aws.usage_start
    AND aws_disk.resource_id = aws.resource_id
LEFT JOIN cte_total_pv_capacity as pv_cap
    ON pv_cap.aws_resource_id = aws.resource_id
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND ocp.persistentvolume is not null
    AND aws.ocp_source = {{ocp_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    -- Filter out Node Network Costs since they cannot be attributed to a namespace and are accounted for later
    AND aws.data_transfer_direction IS NULL
    AND ocp.namespace != 'Storage unattributed'
    AND aws_disk.capacity != pv_cap.total_pv_capacity -- prevent inserting zero cost rows
    AND aws_disk.year = {{year}}
    AND aws_disk.month = {{month}}
    AND aws_disk.ocp_source = {{ocp_source_uuid}}
GROUP BY aws.uuid, aws.resource_id
{% endif %}
;

-- Direct resource_id matching
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp (
    aws_uuid,
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
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    calculated_amortized_cost,
    markup_cost_amortized,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    pod_labels,
    volume_labels,
    tags,
    aws_cost_category,
    cost_category_id,
    resource_id_matched,
    ocp_source,
    year,
    month
)
SELECT aws.uuid as aws_uuid,
        max(ocp.cluster_id) as cluster_id,
        max(ocp.cluster_alias) as cluster_alias,
        'Pod' as data_source,
        ocp.namespace,
        max(ocp.node) as node,
        cast(NULL as varchar) as persistentvolumeclaim,
        cast(NULL as varchar) as persistentvolume,
        cast(NULL as varchar) as storageclass,
        max(aws.resource_id) as resource_id,
        max(aws.usage_start) as usage_start,
        max(aws.usage_start) as usage_end,
        max(aws.product_code) as product_code,
        max(aws.product_family) as product_family,
        max(aws.instance_type) as instance_type,
        max(aws.usage_account_id) as usage_account_id,
        max(aws.availability_zone) as availability_zone,
        max(aws.region) as region,
        max(aws.unit) as unit,
        max(aws.usage_amount) as usage_amount,
        max(aws.currency_code) as currency_code,
        max(aws.unblended_cost) as unblended_cost,
        max(aws.unblended_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(aws.blended_cost) as blended_cost,
        max(aws.blended_cost) * cast({{markup}} as decimal(33,15)) as markup_cost_blended,
        max(aws.savingsplan_effective_cost) as savingsplan_effective_cost,
        max(aws.savingsplan_effective_cost) * cast({{markup}} as decimal(33,15)) as markup_cost_savingsplan,
        max(aws.calculated_amortized_cost) as calculated_amortized_cost,
        max(aws.calculated_amortized_cost) * cast({{markup}} as decimal(33,9)) as markup_cost_amortized,
        sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
        sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
        sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
        sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
        sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
        sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
        sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
        max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        ocp.pod_labels,
        NULL as volume_labels,
        max(aws.tags) as tags,
        max(aws.aws_cost_category) as aws_cost_category,
        max(ocp.cost_category_id) as cost_category_id,
        max(aws.resource_id_matched) as resource_id_matched,
        {{ocp_source_uuid}} as ocp_source,
        max(aws.year) as year,
        max(aws.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp as aws
        ON aws.usage_start = ocp.usage_start
            AND strpos(aws.resource_id, ocp.resource_id) != 0
    LEFT JOIN hive.{{schema | sqlsafe}}.aws_openshift_disk_capacities_temp AS aws_disk
        ON aws_disk.usage_start = aws.usage_start
        AND aws_disk.resource_id = aws.resource_id
        AND aws_disk.year = aws.year
        AND aws_disk.month = aws.month
        AND aws_disk.ocp_source = aws.ocp_source
    WHERE ocp.source = {{ocp_source_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.day IN {{days | inclause}}
        AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
        AND aws.ocp_source = {{ocp_source_uuid}}
        AND aws.year = {{year}}
        AND aws.month = {{month}}
        -- Filter out Node Network Costs since they cannot be attributed to a namespace and are accounted for later
        AND aws.data_transfer_direction IS NULL
        AND aws_disk.resource_id is NULL -- exclude any resource used in disk capacity calculations
    GROUP BY aws.uuid, ocp.namespace, ocp.pod_labels
;

-- Tag matching
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp (
    aws_uuid,
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
    usage_account_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    calculated_amortized_cost,
    markup_cost_amortized,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    pod_labels,
    volume_labels,
    tags,
    aws_cost_category,
    cost_category_id,
    resource_id_matched,
    ocp_source,
    year,
    month
)
SELECT aws.uuid as aws_uuid,
        max(ocp.cluster_id) as cluster_id,
        max(ocp.cluster_alias) as cluster_alias,
        ocp.data_source,
        ocp.namespace,
        max(ocp.node) as node,
        max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
        max(nullif(ocp.persistentvolume, '')) as persistentvolume,
        max(nullif(ocp.storageclass, '')) as storageclass,
        max(aws.resource_id) as resource_id,
        max(aws.usage_start) as usage_start,
        max(aws.usage_start) as usage_end,
        max(aws.product_code) as product_code,
        max(aws.product_family) as product_family,
        max(aws.instance_type) as instance_type,
        max(aws.usage_account_id) as usage_account_id,
        max(aws.availability_zone) as availability_zone,
        max(aws.region) as region,
        max(aws.unit) as unit,
        max(aws.usage_amount) as usage_amount,
        max(aws.currency_code) as currency_code,
        max(aws.unblended_cost) as unblended_cost,
        max(aws.unblended_cost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(aws.blended_cost) as blended_cost,
        max(aws.blended_cost) * cast({{markup}} as decimal(33,15)) as markup_cost_blended,
        max(aws.savingsplan_effective_cost) as savingsplan_effective_cost,
        max(aws.savingsplan_effective_cost) * cast({{markup}} as decimal(33,15)) as markup_cost_savingsplan,
        max(aws.calculated_amortized_cost) as calculated_amortized_cost,
        max(aws.calculated_amortized_cost) * cast({{markup}} as decimal(33,9)) as markup_cost_amortized,
        cast(NULL as double) as pod_usage_cpu_core_hours,
        cast(NULL as double) as pod_request_cpu_core_hours,
        cast(NULL as double) as pod_effective_usage_cpu_core_hours,
        cast(NULL as double) as pod_limit_cpu_core_hours,
        cast(NULL as double) as pod_usage_memory_gigabyte_hours,
        cast(NULL as double) as pod_request_memory_gigabyte_hours,
        cast(NULL as double) as pod_effective_usage_memory_gigabyte_hours,
        cast(NULL as double) as node_capacity_cpu_core_hours,
        cast(NULL as double) as node_capacity_memory_gigabyte_hours,
        cast(NULL as double) as cluster_capacity_cpu_core_hours,
        cast(NULL as double) as cluster_capacity_memory_gigabyte_hours,
        max(ocp.pod_labels) as pod_labels,
        max(ocp.volume_labels) as volume_labels,
        max(aws.tags) as tags,
        max(aws.aws_cost_category) as aws_cost_category,
        max(ocp.cost_category_id) as cost_category_id,
        FALSE as resource_id_matched,
        {{ocp_source_uuid}} as ocp_source,
        max(aws.year) as year,
        max(aws.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_tag_matched_temp as aws
        ON aws.usage_start = ocp.usage_start
            AND (
                json_query(aws.tags, 'strict $.openshift_project' OMIT QUOTES) = ocp.namespace
                OR json_query(aws.tags, 'strict $.openshift_node' OMIT QUOTES) = ocp.node
                OR json_query(aws.tags, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_alias
                OR json_query(aws.tags, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_id
                OR (aws.matched_tag != '' AND any_match(split(aws.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                OR (aws.matched_tag != '' AND any_match(split(aws.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
        AND namespace != 'Worker unallocated'
        AND namespace != 'Platform unallocated'
        AND namespace != 'Storage unattributed'
        AND namespace != 'Network unattributed'
    WHERE ocp.source = {{ocp_source_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.day IN {{days | inclause}}
        AND aws.ocp_source = {{ocp_source_uuid}}
        AND aws.year = {{year}}
        AND aws.month = {{month}}
    GROUP BY aws.uuid, ocp.namespace, ocp.data_source
;

-- Group by to calculate proper cost per project
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary (
    aws_uuid,
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
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
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
    aws_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_rankings AS (
    SELECT pds.aws_uuid,
        count(*) as aws_uuid_count
    FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp AS pds
    WHERE pds.ocp_source = {{ocp_source_uuid}} AND year = {{year}} AND month = {{month}}
    GROUP BY aws_uuid
)
SELECT pds.aws_uuid,
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
    usage_account_id,
    aa.id as account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount / aws_uuid_count as usage_amount,
    NULL AS data_transfer_direction,
    currency_code,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * unblended_cost
        ELSE unblended_cost / aws_uuid_count
    END as unblended_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * blended_cost
        ELSE blended_cost / aws_uuid_count
    END as blended_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * blended_cost * cast({{markup}} as decimal(24,9))
        ELSE blended_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost_blended,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * savingsplan_effective_cost
        ELSE savingsplan_effective_cost / aws_uuid_count
    END as savingsplan_effective_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * savingsplan_effective_cost * cast({{markup}} as decimal(24,9))
        ELSE savingsplan_effective_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost_savingsplan,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * calculated_amortized_cost
        ELSE calculated_amortized_cost / aws_uuid_count
    END as calculated_amortized_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / nullif({{node_column | sqlsafe}}, 0)) * calculated_amortized_cost * cast({{markup}} as decimal(33,9))
        ELSE calculated_amortized_cost / aws_uuid_count * cast({{markup}} as decimal(33,9))
    END as markup_cost_amortized,
    pds.pod_labels,
    CASE WHEN pds.pod_labels IS NOT NULL
        THEN json_format(cast(
            map_concat(
                cast(json_parse(pds.pod_labels) as map(varchar, varchar)),
                cast(json_parse(pds.tags) as map(varchar, varchar))
            ) as JSON))
        ELSE json_format(cast(
            map_concat(
                cast(json_parse(pds.volume_labels) as map(varchar, varchar)),
                cast(json_parse(pds.tags) as map(varchar, varchar))
            ) as JSON))
    END as tags,
    aws_cost_category,
    cost_category_id,
    {{aws_source_uuid}} as aws_source,
    {{ocp_source_uuid}} as ocp_source,
    cast(year(usage_start) as varchar) as year,
    cast(month(usage_start) as varchar) as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp AS pds
JOIN cte_rankings as r
    ON pds.aws_uuid = r.aws_uuid
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON pds.usage_account_id = aa.account_id
WHERE pds.ocp_source = {{ocp_source_uuid}} AND year = {{year}} AND month = {{month}}
;

-- Put Node Network Costs into the Network unattributed namespace
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary (
    aws_uuid,
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
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
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
    aws_source,
    ocp_source,
    year,
    month,
    day
)
SELECT
    aws.uuid AS aws_uuid,
    max(cluster_id),
    max(cluster_alias),
    max(data_source),
    'Network unattributed' AS namespace,
    ocp.node AS node,
    max(persistentvolumeclaim),
    max(persistentvolume),
    max(storageclass),
    max(aws.resource_id),
    max(aws.usage_start),
    max(usage_end),
    max(product_code),
    max(product_family),
    max(instance_type),
    max(usage_account_id),
    max(aa.id) AS account_alias_id,
    max(availability_zone),
    max(region),
    max(unit),
    max(usage_amount),
    data_transfer_direction,
    max(currency_code),
    max(unblended_cost),
    max(unblended_cost) * cast({{markup}} AS decimal(24,9)),
    max(blended_cost),
    max(blended_cost) * cast({{markup}} AS decimal(24,9)),
    max(savingsplan_effective_cost),
    max(savingsplan_effective_cost) * cast({{markup}} AS decimal(24,9)),
    max(calculated_amortized_cost),
    max(calculated_amortized_cost) * cast({{markup}} AS decimal(33,9)),
    max(ocp.pod_labels),
    cast(NULL AS varchar) AS tags,
    cast(NULL AS varchar) AS aws_cost_category,
    max({{aws_source_uuid}}) AS aws_source,
    max({{ocp_source_uuid}}) AS ocp_source,
    max(cast(year(aws.usage_start) AS varchar)) AS year,
    max(cast(month(aws.usage_start) AS varchar)) AS month,
    max(cast(day(aws.usage_start) AS varchar)) AS day
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary AS ocp
JOIN hive.{{schema | sqlsafe}}.aws_openshift_daily_resource_matched_temp AS aws
    ON aws.usage_start = ocp.usage_start
    AND strpos(aws.resource_id, ocp.resource_id) != 0
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON aws.usage_account_id = aa.account_id
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND aws.ocp_source = {{ocp_source_uuid}}
    AND aws.year = {{year}}
    AND aws.month = {{month}}
    -- Network related costs
    AND aws.data_transfer_direction IS NOT NULL
    -- Storage and Pod can have the same resource_id and we want the Pod
    AND ocp.data_source = 'Pod'
GROUP BY
    aws.uuid,
    ocp.node,
    aws.data_transfer_direction
;

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
    json_parse(tags),
    json_parse(aws_cost_category),
    cost_category_id,
    cast(aws_source as UUID)
FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary
WHERE aws_source = {{aws_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN {{days | inclause}}
;
