-- First we'll store the data in a "temp" table to do our grouping against
CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.gcp_openshift_daily_resource_matched_temp
(
    uuid varchar,
    usage_start timestamp,
    account_id varchar,
    project_id varchar,
    project_name varchar,
    resource_name varchar,
    instance_type varchar,
    service_id varchar,
    service_alias varchar,
    data_transfer_direction varchar,
    sku_id varchar,
    sku_alias varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency varchar,
    invoice_month varchar,
    credit_amount double,
    unblended_cost double,
    labels varchar,
    ocp_matched boolean,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.gcp_openshift_daily_tag_matched_temp
(
    uuid varchar,
    usage_start timestamp,
    account_id varchar,
    project_id varchar,
    project_name varchar,
    resource_name varchar,
    instance_type varchar,
    service_id varchar,
    service_alias varchar,
    sku_id varchar,
    sku_alias varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency varchar,
    invoice_month varchar,
    credit_amount double,
    unblended_cost double,
    labels varchar,
    matched_tag varchar,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp
(
    gcp_uuid varchar,
    cluster_id varchar,
    cluster_alias varchar,
    data_source varchar,
    namespace varchar,
    node varchar,
    persistentvolumeclaim varchar,
    persistentvolume varchar,
    storageclass varchar,
    pod_labels varchar,
    resource_id varchar,
    usage_start timestamp,
    usage_end timestamp,
    account_id varchar,
    project_id varchar,
    project_name varchar,
    instance_type varchar,
    service_id varchar,
    service_alias varchar,
    sku_id varchar,
    sku_alias varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency varchar,
    invoice_month varchar,
    credit_amount double,
    unblended_cost double,
    markup_cost double,
    project_markup_cost double,
    pod_cost double,
    pod_credit double,
    pod_usage_cpu_core_hours double,
    pod_request_cpu_core_hours double,
    pod_effective_usage_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    pod_effective_usage_memory_gigabyte_hours double,
    cluster_capacity_cpu_core_hours double,
    cluster_capacity_memory_gigabyte_hours double,
    node_capacity_cpu_core_hours double,
    node_capacity_memory_gigabyte_hours double,
    volume_labels varchar,
    tags varchar,
    cost_category_id int,
    project_rank integer,
    data_source_rank integer,
    ocp_matched boolean,
    ocp_source varchar,
    year varchar,
    month varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['ocp_source', 'year', 'month'])
;

-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary
(
    gcp_uuid varchar,
    cluster_id varchar,
    cluster_alias varchar,
    data_source varchar,
    namespace varchar,
    node varchar,
    persistentvolumeclaim varchar,
    persistentvolume varchar,
    storageclass varchar,
    pod_labels varchar,
    resource_id varchar,
    usage_start timestamp,
    usage_end timestamp,
    account_id varchar,
    project_id varchar,
    project_name varchar,
    instance_type varchar,
    service_id varchar,
    service_alias varchar,
    data_transfer_direction varchar,
    sku_id varchar,
    sku_alias varchar,
    region varchar,
    unit varchar,
    usage_amount double,
    currency varchar,
    invoice_month varchar,
    credit_amount double,
    unblended_cost double,
    markup_cost double,
    project_markup_cost double,
    pod_cost double,
    pod_credit double,
    pod_usage_cpu_core_hours double,
    pod_request_cpu_core_hours double,
    pod_limit_cpu_core_hours double,
    pod_usage_memory_gigabyte_hours double,
    pod_request_memory_gigabyte_hours double,
    cluster_capacity_cpu_core_hours double,
    cluster_capacity_memory_gigabyte_hours double,
    node_capacity_cpu_core_hours double,
    node_capacity_memory_gigabyte_hours double,
    volume_labels varchar,
    tags varchar,
    cost_category_id int,
    project_rank integer,
    data_source_rank integer,
    gcp_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['gcp_source', 'ocp_source', 'year', 'month', 'day'])
;

INSERT INTO hive.{{schema | sqlsafe}}.gcp_openshift_daily_resource_matched_temp (
    uuid,
    usage_start,
    account_id,
    project_id,
    project_name,
    resource_name,
    instance_type,
    service_id,
    service_alias,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    labels,
    ocp_matched,
    ocp_source,
    year,
    month
)
SELECT cast(uuid() as varchar),
    gcp.usage_start_time as usage_start,
    max(gcp.billing_account_id) as account_id,
    gcp.project_id as project_id,
    max(gcp.project_name) as project_name,
    gcp.resource_name,
    json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]') as instance_type,
    gcp.service_id,
    max(nullif(gcp.service_description, '')) as service_alias,
    CASE
        WHEN service_description = 'Compute Engine' AND STRPOS(lower(sku_description), 'data transfer in') != 0 THEN 'IN'
        WHEN service_description = 'Compute Engine' AND STRPOS(lower(sku_description), 'data transfer') != 0 THEN 'OUT'
        ELSE NULL
    END as data_transfer_direction,
    max(nullif(gcp.sku_id, '')) as sku_id,
    max(nullif(gcp.sku_description, '')) as sku_alias,
    gcp.location_region as region,
    max(gcp.usage_pricing_unit) as unit,
    cast(sum(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    max(gcp.currency) as currency,
    gcp.invoice_month as invoice_month,
    -- coalesce for 3 months
    sum(coalesce(credits_amount, daily_credits)) as credit_amount,
    cast(sum(gcp.cost) AS decimal(24,9)) as unblended_cost,
    gcp.labels,
    max(gcp.ocp_matched) as ocp_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
WHERE gcp.source = {{gcp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    AND TRIM(LEADING '0' FROM gcp.day) IN {{days | inclause}} -- external partitions have a leading zero
    AND gcp.ocp_source_uuid = {{ocp_source_uuid}}
    AND gcp.ocp_matched = TRUE
GROUP BY gcp.usage_start_time,
    gcp.project_id,
    gcp.resource_name,
    gcp.system_labels,
    gcp.service_id,
    gcp.location_region,
    gcp.invoice_month,
    gcp.labels,
    10 -- data transfer direction
;

INSERT INTO hive.{{schema | sqlsafe}}.gcp_openshift_daily_tag_matched_temp (
    uuid,
    usage_start,
    account_id,
    project_id,
    project_name,
    resource_name,
    instance_type,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    labels,
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
        AND provider_type = 'GCP'
)
SELECT cast(uuid() as varchar),
    gcp.usage_start_time as usage_start,
    max(gcp.billing_account_id) as account_id,
    gcp.project_id as project_id,
    max(gcp.project_name) as project_name,
    gcp.resource_name,
    json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]') as instance_type,
    gcp.service_id,
    max(nullif(gcp.service_description, '')) as service_alias,
    max(nullif(gcp.sku_id, '')) as sku_id,
    max(nullif(gcp.sku_description, '')) as sku_alias,
    gcp.location_region as region,
    max(gcp.usage_pricing_unit) as unit,
    cast(sum(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    max(gcp.currency) as currency,
    gcp.invoice_month as invoice_month,
    -- coalesce for 3 months
    sum(coalesce(credits_amount, daily_credits)) as credit_amount,
    cast(sum(gcp.cost) AS decimal(24,9)) as unblended_cost,
    -- gcp.labels,
    json_format(
        cast(
            map_filter(
                cast(json_parse(gcp.labels) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as labels,
    gcp.matched_tag,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
CROSS JOIN cte_enabled_tag_keys as etk
WHERE gcp.source = {{gcp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    AND TRIM(LEADING '0' FROM gcp.day) IN {{days | inclause}} -- external partitions have a leading zero
    AND (gcp.ocp_matched = FALSE OR gcp.ocp_matched IS NULL)
GROUP BY gcp.usage_start_time,
    gcp.project_id,
    gcp.resource_name,
    gcp.system_labels,
    gcp.service_id,
    gcp.location_region,
    gcp.invoice_month,
    19, -- label matching
    gcp.matched_tag
;

-- Direct resource_id matching
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    gcp_uuid,
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    markup_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    ocp_matched,
    ocp_source,
    year,
    month
)
SELECT gcp.uuid as gcp_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    ocp.pod_labels,
    max(ocp.resource_id) as resource_id,
    max(gcp.usage_start) as usage_start,
    max(gcp.usage_start) as usage_end,
    max(gcp.account_id) as account_id,
    max(gcp.project_id) as project_id,
    max(gcp.project_name) as project_name,
    max(instance_type) as instance_type,
    max(nullif(gcp.service_id, '')) as service_id,
    max(gcp.service_alias) as service_alias,
    max(gcp.sku_id) as sku_id,
    max(gcp.sku_alias) as sku_alias,
    max(nullif(gcp.region, '')) as region,
    max(gcp.unit) as unit,
    max(gcp.usage_amount) as usage_amount,
    max(gcp.currency) as currency,
    max(gcp.invoice_month) as invoice_month,
    max(gcp.credit_amount) as credit_amount,
    max(gcp.unblended_cost) as unblended_cost,
    max(gcp.unblended_cost * {{markup | sqlsafe}}) as markup_cost,
    sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
    sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    ocp.volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    max(gcp.ocp_matched) as ocp_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.gcp_openshift_daily_resource_matched_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            (strpos(gcp.resource_name, ocp.node) != 0 AND ocp.data_source='Pod')
            OR (strpos(gcp.resource_name, ocp.persistentvolume) != 0 AND ocp.data_source='Storage')
        )
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter out Node Network Costs because they cannot be tied to namespace level
    AND data_transfer_direction IS NULL
GROUP BY gcp.uuid, ocp.namespace, ocp.data_source, ocp.pod_labels, ocp.volume_labels
;

-- direct tag matching, these costs are split evenly between pod and storage since we don't have the info to quantify them separately
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    gcp_uuid,
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    markup_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    ocp_matched,
    ocp_source,
    year,
    month
)
SELECT gcp.uuid as gcp_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(ocp.pod_labels) as pod_labels,
    max(ocp.resource_id) as resource_id,
    max(gcp.usage_start) as usage_start,
    max(gcp.usage_start) as usage_end,
    max(gcp.account_id) as account_id,
    max(gcp.project_id) as project_id,
    max(gcp.project_name) as project_name,
    max(instance_type) as instance_type,
    max(nullif(gcp.service_id, '')) as service_id,
    max(gcp.service_alias) as service_alias,
    max(gcp.sku_id) as sku_id,
    max(gcp.sku_alias) as sku_alias,
    max(nullif(gcp.region, '')) as region,
    max(gcp.unit) as unit,
    max(gcp.usage_amount) as usage_amount,
    max(gcp.currency) as currency,
    max(gcp.invoice_month) as invoice_month,
    max(gcp.credit_amount) as credit_amount,
    max(gcp.unblended_cost) as unblended_cost,
    max(gcp.unblended_cost * {{markup | sqlsafe}}) as markup_cost,
    sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
    sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(ocp.volume_labels) as volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    FALSE as ocp_matched,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.gcp_openshift_daily_tag_matched_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
                json_query(gcp.labels, 'strict $.openshift_project' OMIT QUOTES) = ocp.namespace
                OR json_query(gcp.labels, 'strict $.openshift_node' OMIT QUOTES) = ocp.node
                OR json_query(gcp.labels, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_alias
                OR json_query(gcp.labels, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_id
                OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
    AND ocp.namespace != 'Worker unallocated'
    AND ocp.namespace != 'Platform unallocated'
    AND ocp.namespace != 'Network unattributed'
    AND ocp.namespace != 'Storage unattributed'
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.report_period_id = {{report_period_id}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND gcp.ocp_source = {{ocp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
GROUP BY gcp.uuid, ocp.namespace, ocp.data_source, gcp.invoice_month
;

-- Group by to calculate proper cost per project
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary (
    gcp_uuid,
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    markup_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    gcp_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_rankings AS (
    SELECT pds.gcp_uuid,
        count(*) as gcp_uuid_count
    FROM hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp AS pds
    WHERE pds.ocp_source = {{ocp_source_uuid}} AND year = {{year}} AND month = {{month}}
    GROUP BY gcp_uuid
)
SELECT pds.gcp_uuid,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
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
    END as pod_labels,
    resource_id,
    usage_start,
    usage_end,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    NULL as data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount / r.gcp_uuid_count as usage_amount,
    currency,
    invoice_month,
    CASE WHEN ocp_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * credit_amount
        ELSE credit_amount / r.gcp_uuid_count
    END as credit_amount,
    CASE WHEN ocp_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / r.gcp_uuid_count
    END as unblended_cost,
    CASE WHEN ocp_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / r.gcp_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    {{gcp_source_uuid}} as gcp_source,
    {{ocp_source_uuid}} as ocp_source,
    cast(year(usage_start) as varchar) as year,
    cast(month(usage_start) as varchar) as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp as pds
JOIN cte_rankings as r
    ON pds.gcp_uuid = r.gcp_uuid
WHERE pds.ocp_source = {{ocp_source_uuid}} AND pds.year = {{year}} AND pds.month = {{month}}
;

-- Network costs are currently not mapped to pod metrics
-- and are filtered out of the above SQL since that is grouped by namespace
-- and costs are split out by pod metrics, this puts all network costs per node
-- into a "Network unattributed" project with no cost split and one record per
-- data direction
INSERT INTO hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary (
    gcp_uuid,
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    invoice_month,
    credit_amount,
    unblended_cost,
    markup_cost,
    tags,
    gcp_source,
    ocp_source,
    year,
    month,
    day
)
SELECT gcp.uuid as gcp_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    max(ocp.data_source),
    'Network unattributed' as namespace,
    ocp.node as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(ocp.resource_id) as resource_id,
    max(gcp.usage_start) as usage_start,
    max(gcp.usage_start) as usage_end,
    max(gcp.account_id) as account_id,
    max(gcp.project_id) as project_id,
    max(gcp.project_name) as project_name,
    max(instance_type) as instance_type,
    max(nullif(gcp.service_id, '')) as service_id,
    max(gcp.service_alias) as service_alias,
    max(data_transfer_direction) as data_transfer_direction,
    max(gcp.sku_id) as sku_id,
    max(gcp.sku_alias) as sku_alias,
    max(nullif(gcp.region, '')) as region,
    max(gcp.unit) as unit,
    max(gcp.usage_amount) as usage_amount,
    max(gcp.currency) as currency,
    max(gcp.invoice_month) as invoice_month,
    max(gcp.credit_amount) as credit_amount,
    max(gcp.unblended_cost) as unblended_cost,
    max(gcp.unblended_cost * {{markup | sqlsafe}}) as markup_cost,
    max(gcp.labels) as tags,
    {{gcp_source_uuid}} as gcp_source,
    {{ocp_source_uuid}} as ocp_source,
    cast(year(max(gcp.usage_start)) as varchar) as year,
    cast(month(max(gcp.usage_start)) as varchar) as month,
    cast(day(max(gcp.usage_start)) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.gcp_openshift_daily_resource_matched_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            (strpos(gcp.resource_name, ocp.node) != 0 AND ocp.data_source='Pod')
        )
WHERE ocp.source = {{ocp_source_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter for Node Network Costs to tie them to the Network unattributed project
    AND data_transfer_direction IS NOT NULL
GROUP BY gcp.uuid, ocp.node
;

INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p (
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    infrastructure_data_in_gigabytes,
    infrastructure_data_out_gigabytes,
    data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    tags,
    cost_category_id,
    source_uuid,
    credit_amount,
    invoice_month
)
SELECT uuid(),
    {{report_period_id}} as report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    json_parse(pod_labels),
    resource_id,
    date(usage_start),
    date(usage_start) as usage_end,
    {{bill_id}} as cost_entry_bill_id,
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    CASE
        WHEN upper(data_transfer_direction) = 'IN' THEN
            -- GCP uses gibibyte but we are tracking this field in gigabytes
            CASE unit
                WHEN 'gibibyte' THEN usage_amount * 1.07374
                ELSE usage_amount
            END
        ELSE 0
    END as infrastructure_data_in_gigabytes,
    CASE
        WHEN upper(data_transfer_direction) = 'OUT' THEN
            -- GCP uses gibibyte but we are tracking this field in gigabytes
            CASE unit
                WHEN 'gibibyte' THEN usage_amount * 1.07374
                ELSE usage_amount
            END
        ELSE 0
    END as infrastructure_data_out_gigabytes,
    data_transfer_direction as data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    json_parse(tags),
    cost_category_id,
    cast(gcp_source as UUID),
    credit_amount,
    invoice_month
FROM hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary
WHERE gcp_source = {{gcp_source_uuid}}
    AND ocp_source = {{ocp_source_uuid}}
    AND year = {{year}}
    AND lpad(month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND day IN {{days | inclause}}
;
