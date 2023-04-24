-- First we'll store the data in a "temp" table to do our grouping against
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
    project_rank integer,
    data_source_rank integer,
    cost_category_id int,
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
    project_rank integer,
    data_source_rank integer,
    cost_category_id int,
    gcp_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['gcp_source', 'ocp_source', 'year', 'month', 'day'])
;

-- OCP ON GCP kubernetes-io-cluster-{cluster_id} label is applied on the VM and is exclusively a pod cost
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
    project_markup_cost,
    pod_cost,
    pod_credit,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
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
    cast(NULL as varchar) as persistentvolumeclaim,
    cast(NULL as varchar) as persistentvolume,
    cast(NULL as varchar) as storageclass,
    ocp.pod_labels,
    max(ocp.resource_id) as resource_id,
    max(gcp.usage_start_time) as usage_start,
    max(gcp.usage_start_time) as usage_end,
    max(gcp.billing_account_id) as account_id,
    max(gcp.project_id) as project_id,
    max(gcp.project_name) as project_name,
    max(json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]')) as instance_type,
    max(nullif(gcp.service_id, '')) as service_id,
    max(nullif(gcp.service_description, '')) as service_alias,
    max(nullif(gcp.sku_id, '')) as sku_id,
    max(nullif(gcp.sku_description, '')) as sku_alias,
    max(nullif(gcp.location_region, '')) as region,
    max(gcp.usage_pricing_unit) as unit,
    cast(max(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    max(gcp.currency) as currency,
    gcp.invoice_month as invoice_month,
    max(daily_credits) as credit_amount,
    cast(max(gcp.cost) AS decimal(24,9)) as unblended_cost,
    cast(max(gcp.cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
    cast(NULL as double) AS project_markup_cost,
    cast(NULL AS double) AS pod_cost,
    cast(NULL AS double) AS pod_credit,
    sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
    sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    ocp.volume_labels,
    max(json_format(json_parse(gcp.labels))) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
JOIN hive.{{ schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    ON date(gcp.usage_start_time) = ocp.usage_start
        AND (strpos(gcp.labels, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0 -- THIS IS THE SPECIFIC TO OCP ON GCP TAG MATCH
            OR strpos(gcp.labels, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
WHERE gcp.source = {{gcp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    AND TRIM(LEADING '0' FROM gcp.day) IN {{days | inclause}} -- external partitions have a leading zero
    AND gcp.ocp_source_uuid = {{ocp_source_uuid}}
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
    AND ocp.source = {{ocp_source_uuid}}
    AND ocp.report_period_id = {{report_period_id | sqlsafe}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND ocp.data_source = 'Pod' -- this cost is only associated with pod costs
GROUP BY gcp.uuid, ocp.namespace, gcp.invoice_month, ocp.data_source, ocp.pod_labels, ocp.volume_labels
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
    project_markup_cost,
    pod_cost,
    pod_credit,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
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
    max(gcp.usage_start_time) as usage_start,
    max(gcp.usage_start_time) as usage_end,
    max(gcp.billing_account_id) as account_id,
    max(gcp.project_id) as project_id,
    max(gcp.project_name) as project_name,
    max(json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]')) as instance_type,
    max(nullif(gcp.service_id, '')) as service_id,
    max(nullif(gcp.service_description, '')) as service_alias,
    max(nullif(gcp.sku_id, '')) as sku_id,
    max(nullif(gcp.sku_description, '')) as sku_alias,
    max(nullif(gcp.location_region, '')) as region,
    max(gcp.usage_pricing_unit) as unit,
    cast(max(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
    max(gcp.currency) as currency,
    gcp.invoice_month as invoice_month,
    max(daily_credits) as credit_amount,
    cast(max(gcp.cost) AS decimal(24,9)) as unblended_cost,
    cast(max(gcp.cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
    cast(NULL as double) AS project_markup_cost,
    cast(NULL AS double) AS pod_cost,
    cast(NULL AS double) AS pod_credit,
    sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
    sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
    sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
    sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
    max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
    max(ocp.volume_labels) as volume_labels,
    max(json_format(json_parse(gcp.labels))) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    {{ocp_source_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
JOIN hive.{{ schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    ON date(gcp.usage_start_time) = ocp.usage_start
        AND (
                (strpos(gcp.labels, 'openshift_project') != 0 AND strpos(gcp.labels, lower(ocp.namespace)) != 0)
                OR (strpos(gcp.labels, 'openshift_node') != 0 AND strpos(gcp.labels, lower(ocp.node)) != 0)
                OR (strpos(gcp.labels, 'openshift_cluster') != 0 AND (strpos(gcp.labels, lower(ocp.cluster_id)) != 0 OR strpos(gcp.labels, lower(ocp.cluster_alias)) != 0))
                -- OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                -- OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
        AND ocp.namespace != 'Worker unallocated'
        AND ocp.namespace != 'Platform unallocated'
LEFT JOIN hive.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_temp AS pds
    ON gcp.uuid = pds.gcp_uuid
WHERE gcp.source = {{gcp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    AND TRIM(LEADING '0' FROM gcp.day) IN {{days | inclause}} -- external partitions have a leading zero
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
    AND ocp.source = {{ocp_source_uuid}}
    AND ocp.report_period_id = {{report_period_id | sqlsafe}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days | inclause}}
    AND pds.gcp_uuid IS NULL
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
    project_markup_cost,
    pod_cost,
    pod_credit,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
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
    pds.pod_labels,
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
    usage_amount / r.gcp_uuid_count as usage_amount,
    currency,
    invoice_month,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * credit_amount
        ELSE credit_amount / r.gcp_uuid_count
    END as credit_amount,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / r.gcp_uuid_count
    END as unblended_cost,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / r.gcp_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / r.gcp_uuid_count * cast({{markup}} as decimal(24,9))
    END as project_markup_cost,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / r.gcp_uuid_count
    END as pod_cost,
    CASE WHEN data_source = 'Pod' AND (strpos(tags, 'kubernetes-io-cluster-{{cluster_id | sqlsafe}}') != 0
            OR strpos(tags, 'kubernetes-io-cluster-{{cluster_alias | sqlsafe}}') != 0)
        THEN ({{pod_column | sqlsafe}} / {{cluster_column | sqlsafe}}) * credit_amount
        ELSE credit_amount / r.gcp_uuid_count
    END as pod_credit,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    volume_labels,
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
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    project_markup_cost,
    pod_cost,
    pod_credit,
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
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    project_markup_cost,
    pod_cost,
    pod_credit,
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
