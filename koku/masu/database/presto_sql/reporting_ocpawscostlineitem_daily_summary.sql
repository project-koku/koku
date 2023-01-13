-- First we'll store the data in a "temp" table to do our grouping against
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
    cost_category_id int,
    project_rank integer,
    data_source_rank integer,
    resource_id_matched boolean,
    ocp_source varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source'])
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
    currency_code varchar,
    unblended_cost double,
    markup_cost double,
    blended_cost double,
    markup_cost_blended double,
    savingsplan_effective_cost double,
    markup_cost_savingsplan double,
    pod_cost double,
    project_markup_cost double,
    pod_labels varchar,
    tags varchar,
    cost_category_id int,
    project_rank integer,
    data_source_rank integer,
    aws_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['aws_source', 'ocp_source', 'year', 'month', 'day'])
;

DELETE FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp
WHERE ocp_source = '{{ocp_source_uuid | sqlsafe}}'
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
    pod_cost,
    project_markup_cost,
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
    cost_category_id,
    resource_id_matched,
    ocp_source
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
        max(nullif(aws.lineitem_resourceid, '')) as resource_id,
        max(aws.lineitem_usagestartdate) as usage_start,
        max(aws.lineitem_usagestartdate) as usage_end,
        max(
            CASE
                WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
                ELSE nullif(aws.lineitem_productcode, '')
            END
        ) as product_code,
        max(nullif(aws.product_productfamily, '')) as product_family,
        max(nullif(aws.product_instancetype, '')) as instance_type,
        max(aws.lineitem_usageaccountid) as usage_account_id,
        max(nullif(aws.lineitem_availabilityzone, '')) as availability_zone,
        max(nullif(aws.product_region, '')) as region,
        max(nullif(aws.pricing_unit, '')) as unit,
        max(aws.lineitem_usageamount) as usage_amount,
        max(nullif(aws.lineitem_currencycode, '')) as currency_code,
        max(aws.lineitem_unblendedcost) as unblended_cost,
        max(aws.lineitem_unblendedcost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(aws.lineitem_blendedcost) as blended_cost,
        max(aws.lineitem_blendedcost) * cast({{markup}} as decimal(33,15)) as markup_cost_blended,
        max(aws.savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
        max(aws.savingsplan_savingsplaneffectivecost) * cast({{markup}} as decimal(33,15)) as markup_cost_savingsplan,
        cast(NULL as double) as pod_cost,
        cast(NULL as double) as project_markup_cost,
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
        max(ocp.pod_labels) as pod_labels,
        NULL as volume_labels,
        max(aws.resourcetags) as tags,
        max(ocp.cost_category_id) as cost_category_id,
        max(aws.resource_id_matched) as resource_id_matched,
        '{{ocp_source_uuid | sqlsafe}}' as ocp_source
    FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
    JOIN hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON aws.lineitem_usagestartdate = ocp.usage_start
            AND strpos(aws.lineitem_resourceid, ocp.resource_id) != 0
    WHERE aws.source = '{{aws_source_uuid | sqlsafe}}'
        AND aws.year = {{year}}
        AND aws.month = {{month}}
        AND aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND (aws.lineitem_resourceid IS NOT NULL AND aws.lineitem_resourceid != '')
        AND ocp.source = '{{ocp_source_uuid | sqlsafe}}'
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.day IN ({{days}})
        AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    GROUP BY aws.uuid, ocp.namespace
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
    pod_cost,
    project_markup_cost,
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
    cost_category_id,
    resource_id_matched,
    ocp_source
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
        max(nullif(aws.lineitem_resourceid, '')) as resource_id,
        max(aws.lineitem_usagestartdate) as usage_start,
        max(aws.lineitem_usagestartdate) as usage_end,
        max(
            CASE
                WHEN aws.bill_billingentity='AWS Marketplace' THEN coalesce(nullif(aws.product_productname, ''), nullif(aws.lineitem_productcode, ''))
                ELSE nullif(aws.lineitem_productcode, '')
            END
        ) as product_code,
        max(nullif(aws.product_productfamily, '')) as product_family,
        max(nullif(aws.product_instancetype, '')) as instance_type,
        max(aws.lineitem_usageaccountid) as usage_account_id,
        max(nullif(aws.lineitem_availabilityzone, '')) as availability_zone,
        max(nullif(aws.product_region, '')) as region,
        max(nullif(aws.pricing_unit, '')) as unit,
        max(aws.lineitem_usageamount) as usage_amount,
        max(nullif(aws.lineitem_currencycode, '')) as currency_code,
        max(aws.lineitem_unblendedcost) as unblended_cost,
        max(aws.lineitem_unblendedcost) * cast({{markup}} as decimal(24,9)) as markup_cost,
        max(aws.lineitem_blendedcost) as blended_cost,
        max(aws.lineitem_blendedcost) * cast({{markup}} as decimal(33,15)) as markup_cost_blended,
        max(aws.savingsplan_savingsplaneffectivecost) as savingsplan_effective_cost,
        max(aws.savingsplan_savingsplaneffectivecost) * cast({{markup}} as decimal(33,15)) as markup_cost_savingsplan,
        cast(NULL as double) as pod_cost,
        cast(NULL as double) as project_markup_cost,
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
        max(aws.resourcetags) as tags,
        max(ocp.cost_category_id) as cost_category_id,
        max(aws.resource_id_matched) as resource_id_matched,
        '{{ocp_source_uuid | sqlsafe}}' as ocp_source
    FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
    JOIN hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON aws.lineitem_usagestartdate = ocp.usage_start
            AND (
                (strpos(aws.resourcetags, 'openshift_project') != 0 AND strpos(aws.resourcetags, lower(ocp.namespace)) != 0)
                    OR (strpos(aws.resourcetags, 'namespace') != 0 AND strpos(aws.resourcetags, lower(ocp.namespace)) != 0)
                    OR (strpos(aws.resourcetags, 'openshift_node') != 0 AND strpos(aws.resourcetags, lower(ocp.node)) != 0)
                    OR (strpos(aws.resourcetags, 'openshift_cluster') != 0 AND (strpos(aws.resourcetags, lower(ocp.cluster_id)) != 0 OR strpos(aws.resourcetags, lower(ocp.cluster_alias)) != 0))
                    OR (strpos(aws.resourcetags, 'cluster') != 0 AND (strpos(aws.resourcetags, lower(ocp.cluster_id)) != 0 OR strpos(aws.resourcetags, lower(ocp.cluster_alias)) != 0))
                    OR (aws.matched_tag != '' AND any_match(split(aws.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                    OR (aws.matched_tag != '' AND any_match(split(aws.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
        AND namespace != 'Worker unallocated'
        AND namespace != 'Platform unallocated'
    LEFT JOIN hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp AS pds
        ON aws.uuid = pds.aws_uuid
    WHERE aws.source = '{{aws_source_uuid | sqlsafe}}'
        AND aws.year = {{year}}
        AND aws.month = {{month}}
        AND aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.source = '{{ocp_source_uuid | sqlsafe}}'
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.day IN ({{days}})
        AND pds.aws_uuid IS NULL
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
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    pod_cost,
    project_markup_cost,
    pod_labels,
    tags,
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
    currency_code,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / aws_uuid_count
    END as unblended_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * blended_cost
        ELSE blended_cost / aws_uuid_count
    END as blended_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * blended_cost * cast({{markup}} as decimal(24,9))
        ELSE blended_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost_blended,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * savingsplan_effective_cost
        ELSE savingsplan_effective_cost / aws_uuid_count
    END as savingsplan_effective_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * savingsplan_effective_cost * cast({{markup}} as decimal(24,9))
        ELSE savingsplan_effective_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost_savingsplan,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / aws_uuid_count
    END as pod_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / aws_uuid_count * cast({{markup}} as decimal(24,9))
    END as project_markup_cost,
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
    cost_category_id,
    '{{aws_source_uuid | sqlsafe}}' as aws_source,
    '{{ocp_source_uuid | sqlsafe}}' as ocp_source,
    cast(year(usage_start) as varchar) as year,
    cast(month(usage_start) as varchar) as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp AS pds
JOIN cte_rankings as r
    ON pds.aws_uuid = r.aws_uuid
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON pds.usage_account_id = aa.account_id
WHERE pds.ocp_source = '{{ocp_source_uuid | sqlsafe}}'
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
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    pod_cost,
    project_markup_cost,
    pod_labels,
    tags,
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
    currency_code,
    unblended_cost,
    markup_cost,
    blended_cost,
    markup_cost_blended,
    savingsplan_effective_cost,
    markup_cost_savingsplan,
    pod_cost,
    project_markup_cost,
    json_parse(pod_labels),
    json_parse(tags),
    cost_category_id,
    cast(aws_source as UUID)
FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary
WHERE aws_source = '{{aws_source_uuid | sqlsafe}}'
    AND ocp_source = '{{ocp_source_uuid | sqlsafe}}'
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN ({{days}})
;

DELETE FROM hive.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary_temp
WHERE ocp_source = '{{ocp_source_uuid | sqlsafe}}'
;
