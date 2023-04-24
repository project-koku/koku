-- First we'll store the data in a "temp" table to do our grouping against
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp
(
    azure_uuid varchar,
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
    instance_type varchar,
    subscription_guid varchar,
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
    resource_id_matched boolean,
    cost_category_id int,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary
(
    azure_uuid varchar,
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
    instance_type varchar,
    subscription_guid varchar,
    resource_location varchar,
    unit_of_measure varchar,
    usage_quantity double,
    currency varchar,
    pretax_cost double,
    markup_cost double,
    pod_cost double,
    project_markup_cost double,
    pod_labels varchar,
    tags varchar,
    project_rank integer,
    data_source_rank integer,
    cost_category_id int,
    azure_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['azure_source', 'ocp_source', 'year', 'month', 'day'])
;


-- Directly resource_id matching
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp (
    azure_uuid,
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
    service_name,
    instance_type,
    subscription_guid,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
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
    resource_id_matched,
    cost_category_id,
    ocp_source,
    year,
    month
)
SELECT azure.uuid as azure_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace as namespace,
    max(ocp.node) as node,
    max(persistentvolumeclaim) as persistentvolumeclaim,
    max(persistentvolume) as persistentvolume,
    max(storageclass) as storageclass,
    max(split_part(coalesce(resourceid, instanceid), '/', 9)) as resource_id,
    max(coalesce(date, usagedatetime)) as usage_start,
    max(coalesce(date, usagedatetime)) as usage_end,
    max(nullif(coalesce(servicename, metercategory), '')) as service_name,
    max(json_extract_scalar(json_parse(azure.additionalinfo), '$.ServiceType')) as instance_type,
    max(coalesce(subscriptionid, subscriptionguid)) as subscription_guid,
    max(azure.resourcelocation) as resource_location,
    max(CASE
            WHEN split_part(unitofmeasure, ' ', 2) = 'Hours'
                THEN  'Hrs'
            WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                THEN  'GB-Mo'
            WHEN split_part(unitofmeasure, ' ', 2) != ''
                THEN  split_part(unitofmeasure, ' ', 2)
            ELSE unitofmeasure
        END) as unit_of_measure,
    max(cast(coalesce(azure.quantity, azure.usagequantity) as decimal(24,9))) as usage_quantity,
    max(coalesce(billingcurrencycode, currency)) as currency,
    max(cast(coalesce(azure.costinbillingcurrency, azure.pretaxcost) as decimal(24,9))) as pretax_cost,
    max(cast(coalesce(azure.costinbillingcurrency, azure.pretaxcost) as decimal(24,9))) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
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
    ocp.pod_labels,
    ocp.volume_labels,
    max(azure.tags) as tags,
    max(azure.resource_id_matched) as resource_id_matched,
    max(ocp.cost_category_id) as cost_category_id,
    {{ocp_source_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.azure_openshift_daily as azure
    JOIN hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        on coalesce(azure.date, azure.usagedatetime) = ocp.usage_start
        AND (
                (split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) = ocp.node AND ocp.data_source = 'Pod')
                    OR (split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) = ocp.persistentvolume AND ocp.data_source = 'Storage')
            )
    WHERE azure.source = {{azure_source_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND coalesce(azure.date, azure.usagedatetime) >= {{start_date}}
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, {{end_date}})
        AND ocp.source = {{ocp_source_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    GROUP BY azure.uuid, ocp.namespace, ocp.data_source, ocp.pod_labels, ocp.volume_labels
;

-- Tag matching
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp (
    azure_uuid,
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
    service_name,
    instance_type,
    subscription_guid,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
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
    resource_id_matched,
    cost_category_id,
    ocp_source,
    year,
    month
)
SELECT azure.uuid as azure_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(split_part(coalesce(resourceid, instanceid), '/', 9)) as resource_id,
    max(coalesce(date, usagedatetime)) as usage_start,
    max(coalesce(date, usagedatetime)) as usage_end,
    max(nullif(coalesce(servicename, metercategory), '')) as service_name,
    max(json_extract_scalar(json_parse(azure.additionalinfo), '$.ServiceType')) as instance_type,
    max(coalesce(subscriptionid, subscriptionguid)) as subscription_guid,
    max(nullif(azure.resourcelocation, '')) as resource_location,
    max(CASE
            WHEN split_part(unitofmeasure, ' ', 2) = 'Hours'
                THEN  'Hrs'
            WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                THEN  'GB-Mo'
            WHEN split_part(unitofmeasure, ' ', 2) != ''
                THEN  split_part(unitofmeasure, ' ', 2)
            ELSE unitofmeasure
        END) as unit_of_measure,
    max(cast(coalesce(azure.quantity, azure.usagequantity) as decimal(24,9))) as usage_quantity,
    max(coalesce(billingcurrencycode, azure.currency)) as currency,
    max(cast(coalesce(azure.costinbillingcurrency, azure.pretaxcost) as decimal(24,9))) as pretax_cost,
    max(cast(coalesce(azure.costinbillingcurrency, azure.pretaxcost) as decimal(24,9))) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
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
    max(azure.tags) as tags,
    max(azure.resource_id_matched) as resource_id_matched,
    max(ocp.cost_category_id) as cost_category_id,
    {{ocp_source_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.azure_openshift_daily as azure
    JOIN hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON coalesce(azure.date, azure.usagedatetime) = ocp.usage_start
        AND (
                    (strpos(azure.tags, 'openshift_project') !=0 AND strpos(azure.tags, lower(ocp.namespace)) != 0)
                    OR (strpos(azure.tags, 'openshift_node') != 0 AND strpos(azure.tags,lower(ocp.node)) != 0)
                    OR (strpos(azure.tags, 'openshift_cluster') != 0 AND (strpos(azure.tags, lower(ocp.cluster_id)) != 0 OR strpos(azure.tags, lower(ocp.cluster_alias)) != 0))
                    OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                    OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
        AND namespace != 'Worker unallocated'
        AND namespace != 'Platform unallocated'
    LEFT JOIN hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp AS pds
        ON azure.uuid = pds.azure_uuid
    WHERE azure.source = {{azure_source_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND coalesce(azure.date, azure.usagedatetime) >= {{start_date}}
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, {{end_date}})
        AND ocp.source = {{ocp_source_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND pds.azure_uuid is NULL
    GROUP BY azure.uuid, ocp.namespace, ocp.data_source
;

-- Group by to calculate proper cost per project

INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary (
    azure_uuid,
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
    service_name,
    instance_type,
    subscription_guid,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    pod_cost,
    project_markup_cost,
    pod_labels,
    tags,
    cost_category_id,
    azure_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_rankings AS (
    SELECT pds.azure_uuid,
        count(*) as azure_uuid_count
    FROM hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp AS pds
    GROUP BY azure_uuid
)
SELECT pds.azure_uuid,
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
    service_name,
    instance_type,
    subscription_guid,
    resource_location,
    unit_of_measure,
    usage_quantity / r.azure_uuid_count as usage_quantity,
    currency,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost
        ELSE pretax_cost / r.azure_uuid_count
    END as pretax_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost * cast({{markup}} as decimal(24,9))
        ELSE pretax_cost / r.azure_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost
        ELSE pretax_cost / r.azure_uuid_count
    END as pod_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost * cast({{markup}} as decimal(24,9))
        ELSE pretax_cost / r.azure_uuid_count * cast({{markup}} as decimal(24,9))
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
    {{azure_source_uuid}} as azure_source,
    {{ocp_source_uuid}} as ocp_source,
    cast(year(usage_start) as varchar) as year,
    cast(month(usage_start) as varchar) as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_temp AS pds
JOIN cte_rankings as r
    ON pds.azure_uuid = r.azure_uuid
WHERE pds.ocp_source = {{ocp_source_uuid}} AND pds.year = {{year}} AND pds.month = {{month}}
;

INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary_p (
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
    pod_labels,
    resource_id,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    subscription_guid,
    instance_type,
    service_name,
    resource_location,
    usage_quantity,
    unit_of_measure,
    currency,
    pretax_cost,
    markup_cost,
    project_markup_cost,
    pod_cost,
    tags,
    cost_category_id,
    source_uuid
)
SELECT uuid(),
    {{report_period_id | sqlsafe}} as report_period_id,
    cluster_id as cluster_id,
    cluster_alias as cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    json_parse(pod_labels),
    resource_id,
    date(usage_start),
    date(usage_end),
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
    subscription_guid,
    instance_type,
    service_name,
    resource_location,
    usage_quantity,
    unit_of_measure,
    currency,
    pretax_cost,
    markup_cost,
    project_markup_cost,
    pod_cost,
    json_parse(tags),
    cost_category_id,
    cast(azure_source as UUID)
FROM hive.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary
WHERE azure_source = {{azure_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day in {{days | inclause}}
;
