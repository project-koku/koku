{% if unattributed_storage %}
DELETE FROM hive.{{schema | sqlsafe}}.managed_gcp_openshift_disk_capacities_temp
WHERE ocp_source = {{ocp_provider_uuid}}
AND source = {{cloud_provider_uuid}}
AND year = {{year}}
AND month = {{month}}
{% endif %}
;

{% if unattributed_storage %}
INSERT INTO hive.{{schema | sqlsafe}}.managed_gcp_openshift_disk_capacities_temp (
    resource_global_name,
    resource_name,
    capacity,
    source,
    ocp_source,
    year,
    month
)
SELECT
    gcp.resource_global_name,
    gcp.resource_name,
    max(gcp.usage_amount) / 1073741824.0 / 3600 as capacity,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    {{year}} as year,
    {{month}} as month
FROM hive.{{schema | sqlsafe}}.gcp_line_items as gcp
WHERE gcp.resource_global_name in (
        SELECT temp.resource_global_name as resource_global_name
        FROM hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as temp
        INNER JOIN hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as ocp
            ON temp.usage_start = DATE(ocp.interval_start)
                AND (
                    (ocp.csi_volume_handle != '' AND strpos(temp.resource_global_name, ocp.csi_volume_handle) != 0)
                    OR (ocp.csi_volume_handle != '' AND strpos(temp.resource_name, ocp.csi_volume_handle) != 0)
                )
        WHERE temp.resource_global_name LIKE '%/disk/%'
        AND temp.service_description = 'Compute Engine'
        AND lower(temp.sku_description) LIKE '% pd %'
        AND temp.year = {{year}}
        AND temp.month = {{month}}
        AND temp.source = {{cloud_provider_uuid}}
        AND temp.ocp_source = {{ocp_provider_uuid}}
        AND temp.usage_amount > 0
        AND ocp.interval_start >= {{start_date}}
        AND ocp.interval_start < date_add('day', 1, {{end_date}})
        GROUP BY temp.resource_global_name
    )
    AND month = {{month}}
    AND year = {{year}}
    AND source = {{cloud_provider_uuid}}
GROUP BY gcp.resource_global_name, gcp.resource_name
{% endif %}
;

DELETE FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp
WHERE ocp_source = {{ocp_provider_uuid}}
AND source = {{cloud_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

{%- if unattributed_storage -%}
-- Storage disk resource id matching
-- Algorthim:
-- (PV Capacity) / Disk Capacity * Cost of Disk
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    row_uuid,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_name,
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
    volume_labels,
    tags,
    cost_category_id,
    resource_id_matched,
    source,
    ocp_source,
    year,
    month
)
SELECT
    CASE
        WHEN max(gcp_disk.capacity) < max(ocp.persistentvolumeclaim_capacity_gigabyte) or max(gcp_disk.capacity) = 0
        THEN gcp.row_uuid -- deduplicate if not using cost ratio
        ELSE cast(uuid() as varchar)
    END AS row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    max(ocp.data_source),
    CASE
        WHEN max(persistentvolumeclaim) = ''
            THEN 'Storage unattributed'
        ELSE max(namespace)
    END as namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(gcp.resource_name) as resource_name,
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
    CASE
        WHEN max(gcp_disk.capacity) < max(ocp.persistentvolumeclaim_capacity_gigabyte) or max(gcp_disk.capacity) = 0
        THEN max(gcp.credit_amount)
        ELSE max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(gcp_disk.capacity) * max(gcp.credit_amount)
    END as credit_amount,
    CASE
        WHEN max(gcp_disk.capacity) < max(ocp.persistentvolumeclaim_capacity_gigabyte) or max(gcp_disk.capacity) = 0
        THEN max(gcp.unblended_cost)
        ELSE max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(gcp_disk.capacity) * max(gcp.unblended_cost)
    END as unblended_cost,
    CASE
        WHEN max(gcp_disk.capacity) < max(ocp.persistentvolumeclaim_capacity_gigabyte) or max(gcp_disk.capacity) = 0
        THEN max(gcp.unblended_cost * {{markup | sqlsafe}})
        ELSE max(ocp.persistentvolumeclaim_capacity_gigabyte) / max(gcp_disk.capacity) * max(gcp.unblended_cost * {{markup | sqlsafe}})
    END as markup_cost,
    ocp.volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    TRUE as resource_id_matched,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            strpos(gcp.resource_global_name, ocp.csi_volume_handle) != 0
            OR strpos(gcp.resource_name, ocp.csi_volume_handle) != 0
        )
        AND gcp.ocp_source = ocp.source_uuid
        AND gcp.month = lpad(ocp.month, 2, '0')
        AND gcp.year = ocp.year
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_disk_capacities_temp as gcp_disk
    ON  gcp_disk.resource_global_name = gcp.resource_global_name
        AND gcp_disk.year = gcp.year
        AND gcp_disk.month = gcp.month
        AND gcp_disk.source = gcp.source
        AND gcp_disk.ocp_source = gcp.ocp_source
WHERE ocp.source = {{ocp_provider_uuid}}
    AND ocp.data_source = 'Storage'
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days_tup | inclause}}
    AND (ocp.csi_volume_handle IS NOT NULL AND ocp.csi_volume_handle != '')
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_provider_uuid}}
    AND gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter out Node Network Costs because they cannot be tied to namespace level
    AND data_transfer_direction IS NULL
    AND gcp.resource_id_matched = TRUE
GROUP BY gcp.row_uuid, ocp.namespace, ocp.pod_labels, ocp.volume_labels
{% endif %}
;

{%- if unattributed_storage -%}
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    row_uuid,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    pod_labels,
    resource_name,
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
    pod_effective_usage_cpu_core_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    resource_id_matched,
    source,
    ocp_source,
    year,
    month
)
WITH cte_total_pv_capacity as (
    SELECT
        gcp_resource_name,
        SUM(combined_requests.capacity) as total_pv_capacity,
        count(distinct persistentvolume) as pv_count
    FROM (
        SELECT
            ocp.persistentvolume,
            max(ocp.persistentvolumeclaim_capacity_gigabyte) as capacity,
            gcp.resource_global_name as gcp_resource_name
        FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
            ON (gcp.usage_start = ocp.usage_start)
            AND strpos(gcp.resource_global_name, ocp.csi_volume_handle) > 0
            AND ocp.csi_volume_handle is not null
            AND ocp.csi_volume_handle != ''
        WHERE ocp.year = {{year}}
            AND lpad(ocp.month, 2, '0') = {{month}}
            AND ocp.usage_start >= {{start_date}}
            AND ocp.usage_start < date_add('day', 1, {{end_date}})
            AND gcp.ocp_source = {{ocp_provider_uuid}}
            AND gcp.year = {{year}}
            AND gcp.month = {{month}}
            AND gcp.resource_id_matched = True
        GROUP BY ocp.persistentvolume, gcp.resource_global_name
    ) as combined_requests group by gcp_resource_name
)
SELECT cast(uuid() as varchar) as row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    max(ocp.data_source),
    'Storage unattributed',
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    ocp.pod_labels as pod_labels,
    max(gcp.resource_name) as resource_name,
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
    0 as usage_amount,
    max(gcp.currency) as currency,
    max(gcp.invoice_month) as invoice_month,
    CASE
        WHEN max(gcp_disk.capacity) < max(pv_cap.total_pv_capacity) or max(gcp_disk.capacity) = 0
        THEN max(0)
        ELSE (max(gcp_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(gcp_disk.capacity) * max(gcp.credit_amount) / max(pv_cap.pv_count)
    END as credit_amount,
    CASE
        WHEN max(gcp_disk.capacity) < max(pv_cap.total_pv_capacity) or max(gcp_disk.capacity) = 0
        THEN max(0)
        ELSE (max(gcp_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(gcp_disk.capacity) * max(gcp.unblended_cost) / max(pv_cap.pv_count)
    END as unblended_cost,
    CASE
        WHEN max(gcp_disk.capacity) < max(pv_cap.total_pv_capacity) or max(gcp_disk.capacity) = 0
        THEN max(0)
        ELSE (max(gcp_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(gcp_disk.capacity) * max(gcp.unblended_cost * {{markup | sqlsafe}}) / max(pv_cap.pv_count)
    END as markup_cost,
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    ocp.volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    TRUE as resource_id_matched,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            strpos(gcp.resource_global_name, ocp.csi_volume_handle) != 0
            OR strpos(gcp.resource_name, ocp.csi_volume_handle) != 0
        )
        AND gcp.ocp_source = ocp.source_uuid
        AND gcp.month = lpad(ocp.month, 2, '0')
        AND gcp.year = ocp.year
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_disk_capacities_temp as gcp_disk
    ON gcp_disk.resource_global_name = gcp.resource_global_name
        AND gcp_disk.year = gcp.year
        AND gcp_disk.month = gcp.month
        AND gcp_disk.source = gcp.source
        AND gcp_disk.ocp_source = gcp.ocp_source
LEFT JOIN cte_total_pv_capacity as pv_cap
    ON pv_cap.gcp_resource_name = gcp.resource_global_name
WHERE ocp.source = {{ocp_provider_uuid}}
    AND ocp.data_source = 'Storage'
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days_tup | inclause}}
    AND (ocp.csi_volume_handle IS NOT NULL AND ocp.csi_volume_handle != '')
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_provider_uuid}}
    AND gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter out Node Network Costs because they cannot be tied to namespace level
    AND data_transfer_direction IS NULL
    AND gcp.resource_id_matched = TRUE
GROUP BY gcp.row_uuid, ocp.namespace, ocp.pod_labels, ocp.volume_labels
{%- endif -%}
;

-- Direct resource_id matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    row_uuid,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    pod_labels,
    resource_name,
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
    pod_effective_usage_cpu_core_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    resource_id_matched,
    source,
    ocp_source,
    year,
    month
)
SELECT gcp.row_uuid as row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    ocp.pod_labels as pod_labels,
    max(gcp.resource_name) as resource_name,
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
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    ocp.volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    TRUE as resource_id_matched,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            (strpos(gcp.resource_name, ocp.node) != 0 AND ocp.data_source='Pod')
            OR (strpos(gcp.resource_name, ocp.persistentvolume) != 0 AND ocp.data_source='Storage')
        )
WHERE ocp.source = {{ocp_provider_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days_tup | inclause}}
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_provider_uuid}}
    AND gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter out Node Network Costs because they cannot be tied to namespace level
    AND data_transfer_direction IS NULL
    AND gcp.resource_id_matched = TRUE
GROUP BY gcp.row_uuid, ocp.namespace, ocp.data_source, ocp.pod_labels, ocp.volume_labels
;

-- direct tag matching, these costs are split evenly between pod and storage since we don't have the info to quantify them separately
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp (
    row_uuid,
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
    pod_effective_usage_cpu_core_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month
)
SELECT gcp.row_uuid as row_uuid,
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
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    max(ocp.volume_labels) as volume_labels,
    max(gcp.labels) as tags,
    max(ocp.cost_category_id) as cost_category_id,
    FALSE as resource_id_matched,
    gcp.matched_tag as matched_tag,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(gcp.year) as year,
    max(gcp.month) as month
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
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
WHERE ocp.source = {{ocp_provider_uuid}}
    AND ocp.report_period_id = {{report_period_id}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days_tup | inclause}}
    AND gcp.ocp_source = {{ocp_provider_uuid}}
    AND gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    AND gcp.matched_tag != ''
    AND gcp.resource_id_matched = False
GROUP BY gcp.row_uuid, ocp.namespace, ocp.data_source, gcp.invoice_month, gcp.matched_tag
;

{%- if distribution == 'cpu' -%}
{%- set pod_column = 'pod_effective_usage_cpu_core_hours' -%}
{%- set node_column = 'node_capacity_cpu_core_hours' -%}
{%- else -%}
{%- set pod_column = 'pod_effective_usage_memory_gigabyte_hours' -%}
{%- set node_column = 'node_capacity_memory_gigabyte_hours' -%}
{%- endif -%}
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary (
    row_uuid,
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
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    volume_labels,
    tags,
    cost_category_id,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_rankings AS (
    SELECT pds.row_uuid,
        count(*) as row_uuid_count
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp AS pds
    WHERE pds.ocp_source = {{ocp_provider_uuid}} AND year = {{year}} AND month = {{month}}
    GROUP BY row_uuid
)
SELECT pds.row_uuid,
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
    NULL as data_transfer_direction,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount / r.row_uuid_count as usage_amount,
    currency,
    invoice_month,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * credit_amount
        ELSE credit_amount / r.row_uuid_count
    END as credit_amount,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost
        ELSE unblended_cost / r.row_uuid_count
    END as unblended_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE unblended_cost / r.row_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
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
    resource_id_matched,
    matched_tag,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    cast(year(usage_start) as varchar) as year,
    cast(month(usage_start) as varchar) as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary_temp as pds
JOIN cte_rankings as r
    ON pds.row_uuid = r.row_uuid
WHERE pds.ocp_source = {{ocp_provider_uuid}}
    AND pds.year = {{year}}
    AND pds.month = {{month}}
    AND pds.source = {{cloud_provider_uuid}}
;

-- Network costs are currently not mapped to pod metrics
-- and are filtered out of the above SQL since that is grouped by namespace
-- and costs are split out by pod metrics, this puts all network costs per node
-- into a "Network unattributed" project with no cost split and one record per
-- data direction
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpgcpcostlineitem_project_daily_summary (
    row_uuid,
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
    source,
    ocp_source,
    year,
    month,
    day
)
SELECT gcp.row_uuid as row_uuid,
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
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    cast(year(max(gcp.usage_start)) as varchar) as year,
    cast(month(max(gcp.usage_start)) as varchar) as month,
    cast(day(max(gcp.usage_start)) as varchar) as day
FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
JOIN hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp as gcp
    ON gcp.usage_start = ocp.usage_start
        AND (
            (strpos(gcp.resource_name, ocp.node) != 0 AND ocp.data_source='Pod')
        )
WHERE ocp.source = {{ocp_provider_uuid}}
    AND ocp.year = {{year}}
    AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
    AND ocp.day IN {{days_tup | inclause}}
    AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
    AND gcp.ocp_source = {{ocp_provider_uuid}}
    AND gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month = {{month}}
    -- Filter for Node Network Costs to tie them to the Network unattributed project
    AND data_transfer_direction IS NOT NULL
    AND data_transfer_direction != ''
    AND gcp.resource_id_matched = TRUE
GROUP BY gcp.row_uuid, ocp.node
;
