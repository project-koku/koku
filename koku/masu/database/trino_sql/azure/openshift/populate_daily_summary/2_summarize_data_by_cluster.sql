DELETE FROM hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp
WHERE ocp_source = {{ocp_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

INSERT INTO hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp (
    resource_id,
    capacity,
    usage_start,
    ocp_source,
    year,
    month
)
SELECT
    azure.resource_id,
    max(az_disk_capacity.capacity) as capacity,
    date(azure.date) as usage_start,
    {{ocp_provider_uuid}} as ocp_source,
    {{year}} as year,
    {{month}} as month
FROM hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
JOIN postgres.public.reporting_common_diskcapacity as az_disk_capacity
    ON azure.metername LIKE '%' || az_disk_capacity.product_substring || ' %' -- space here is important to avoid partial matching
    AND az_disk_capacity.provider_type = 'Azure'
WHERE azure.date >= TIMESTAMP '{{start_date | sqlsafe}}'
    AND azure.date < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
    AND azure.service_name LIKE '%Storage%'
    AND azure.complete_resource_id LIKE '%%Microsoft.Compute/disks/%%'
    AND lower(azure.resource_id) NOT LIKE '%%_osdisk'
    AND azure.year = {{year}}
    AND azure.month = {{month}}
    AND azure.ocp_source = {{ocp_provider_uuid}}
    and azure.source = {{cloud_provider_uuid}}
    AND azure.resource_id_matched = True
GROUP BY azure.resource_id, date(date);

DELETE FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp
WHERE ocp_source = {{ocp_provider_uuid}}
AND source = {{cloud_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

-- resource_id matching
-- Storage disk resources:
-- (PV’s Capacity) / Disk Capacity * Cost of Disk
-- PV without PVCs are Unattributed Storage
-- 2 volumes can share the same disk id
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (
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
    service_name,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    pod_labels,
    volume_labels,
    tags,
    resource_id_matched,
    cost_category_id,
    source,
    ocp_source,
    year,
    month
)
SELECT cast(uuid() as varchar) as row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    'Storage' as data_source,
    CASE
        WHEN max(persistentvolumeclaim) = ''
            THEN 'Storage unattributed'
        ELSE max(namespace)
    END as namespace,
    max(ocp.node) as node,
    max(persistentvolumeclaim) as persistentvolumeclaim,
    max(persistentvolume) as persistentvolume,
    max(storageclass) as storageclass,
    max(azure.resource_id) as resource_id,
    max(azure.usage_start) as usage_start,
    max(azure.usage_start) as usage_end,
    max(nullif(azure.service_name, '')) as service_name,
    max(azure.instance_type) as instance_type,
    max(azure.subscription_guid) as subscription_guid,
    max(azure.subscription_name) as subscription_name,
    max(nullif(azure.resource_location, '')) as resource_location,
    'GB-Mo' as unit_of_measure, -- Has to have this unit to show up on ocp on cloud storage endpoint
    max(cast(azure.usage_quantity as decimal(24,9))) as usage_quantity,
    max(azure.currency) as currency,
    max(persistentvolumeclaim_capacity_gigabyte) / max(az_disk.capacity) * max(azure.pretax_cost)  as pretax_cost,
    (max(persistentvolumeclaim_capacity_gigabyte) / max(az_disk.capacity) * max(azure.pretax_cost)) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
    CASE
        WHEN max(persistentvolumeclaim) = ''
            THEN cast(NULL as varchar)
        ELSE ocp.pod_labels
    END as pod_labels,
    CASE
        WHEN max(persistentvolumeclaim) = ''
            THEN cast(NULL as varchar)
        ELSE ocp.volume_labels
    END as volume_labels,
    max(azure.tags) as tags,
    max(azure.resource_id_matched) as resource_id_matched,
    CASE
        WHEN max(persistentvolumeclaim) = ''
            THEN NULL
        ELSE max(ocp.cost_category_id)
    END as cost_category_id,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON (azure.usage_start = ocp.usage_start)
        AND (
                (strpos(azure.resource_id, ocp.persistentvolume) > 0 AND ocp.data_source = 'Storage')
            OR
                (lower(ocp.csi_volume_handle) = lower(azure.resource_id))
            )
        AND azure.ocp_source = ocp.source
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp AS az_disk
        ON az_disk.usage_start = azure.usage_start
        AND az_disk.resource_id = azure.resource_id
        AND az_disk.ocp_source = azure.ocp_source
    WHERE ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND ocp.persistentvolume is not null
        -- Filter out Node Network Costs because they cannot be tied to namespace level
        AND azure.data_transfer_direction IS NULL
        AND azure.ocp_source = {{ocp_provider_uuid}}
        and azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND azure.resource_id_matched = True
        AND ocp.namespace != 'Storage unattributed'
        AND az_disk.year = {{year}}
        AND az_disk.month = {{month}}
        AND az_disk.ocp_source = {{ocp_provider_uuid}}
    GROUP BY azure.row_uuid, ocp.namespace, ocp.data_source, ocp.pod_labels, ocp.volume_labels;

-- Unallocated Cost: ((Disk Capacity - Sum(PV capacity) / Disk Capacity) * Cost of Disk
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (
    row_uuid,
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
    service_name,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    currency,
    pretax_cost,
    markup_cost,
    resource_id_matched,
    source,
    ocp_source,
    year,
    month
)
WITH cte_total_pv_capacity as (
    SELECT
        azure_resource_id,
        SUM(combined_requests.capacity) as total_pv_capacity,
        count(distinct cluster_id) as cluster_count
    FROM (
        SELECT
            ocp.persistentvolume,
            max(ocp.persistentvolumeclaim_capacity_gigabyte) as capacity,
            azure.resource_id as azure_resource_id,
            ocp.cluster_id
        FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON (azure.usage_start = ocp.usage_start)
        AND (
                (strpos(azure.resource_id, ocp.persistentvolume) > 0 AND ocp.data_source = 'Storage')
            OR
                (lower(ocp.csi_volume_handle) = lower(azure.resource_id))
            )
        WHERE ocp.year = {{year}}
            AND lpad(ocp.month, 2, '0') = {{month}}
            AND ocp.usage_start >= {{start_date}}
            AND ocp.usage_start < date_add('day', 1, {{end_date}})
            AND azure.ocp_source = {{ocp_provider_uuid}}
            AND azure.source = {{cloud_provider_uuid}}
            AND azure.year = {{year}}
            AND azure.month = {{month}}
            AND azure.resource_id_matched = True
        GROUP BY ocp.persistentvolume, azure.resource_id, ocp.cluster_id
    ) as combined_requests group by azure_resource_id
)
SELECT cast(uuid() as varchar) as row_uuid, -- need a new uuid or it will deduplicate
        max(ocp.cluster_id) as cluster_id,
        max(ocp.cluster_alias) as cluster_alias,
        'Storage' as data_source,
        'Storage unattributed' as namespace,
        max(persistentvolumeclaim) as persistentvolumeclaim,
        max(persistentvolume) as persistentvolume,
        max(storageclass) as storageclass,
        max(azure.resource_id) as resource_id,
        max(azure.usage_start) as usage_start,
        max(azure.usage_start) as usage_end,
        max(nullif(azure.service_name, '')) as service_name,
        max(azure.instance_type) as instance_type,
        max(azure.subscription_guid) as subscription_guid,
        max(azure.subscription_name) as subscription_name,
        max(nullif(azure.resource_location, '')) as resource_location,
        'GB-Mo' as unit_of_measure, -- Has to have this unit to show up on storage endpoint
        max(azure.currency) as currency,
        (max(az_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(az_disk.capacity) * max(azure.pretax_cost) / max(pv_cap.cluster_count)  as pretax_cost,
        ((max(az_disk.capacity) - max(pv_cap.total_pv_capacity)) / max(az_disk.capacity) * max(azure.pretax_cost)) * cast({{markup}} as decimal(24,9)) / max(pv_cap.cluster_count) as markup_cost, -- pretax_cost x markup = markup_cost
        max(azure.resource_id_matched) as resource_id_matched,
        {{cloud_provider_uuid}} as source,
        {{ocp_provider_uuid}} as ocp_source,
        max(azure.year) as year,
        max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON (azure.usage_start = ocp.usage_start)
        AND (
                (strpos(azure.resource_id, ocp.persistentvolume) > 0 AND ocp.data_source = 'Storage')
            OR
                (lower(ocp.csi_volume_handle) = lower(azure.resource_id))
            )
        AND azure.ocp_source = ocp.source
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp AS az_disk
        ON az_disk.usage_start = azure.usage_start
        AND az_disk.resource_id = azure.resource_id
        AND az_disk.ocp_source = azure.ocp_source
    LEFT JOIN cte_total_pv_capacity as pv_cap
        ON pv_cap.azure_resource_id = azure.resource_id
    WHERE ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}}
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND azure.ocp_source = {{ocp_provider_uuid}}
        AND azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND azure.resource_id_matched = True
        AND ocp.namespace != 'Storage unattributed'
        AND az_disk.year = {{year}}
        AND az_disk.month = {{month}}
    GROUP BY azure.row_uuid, ocp.data_source, azure.resource_id;

-- Directly Pod resource_id matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (
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
    service_name,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    pod_effective_usage_cpu_core_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabyte_hours,
    pod_labels,
    volume_labels,
    tags,
    resource_id_matched,
    cost_category_id,
    source,
    ocp_source,
    year,
    month
)
SELECT azure.row_uuid as row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace as namespace,
    max(ocp.node) as node,
    max(persistentvolumeclaim) as persistentvolumeclaim,
    max(persistentvolume) as persistentvolume,
    max(storageclass) as storageclass,
    max(azure.resource_id) as resource_id,
    max(azure.usage_start) as usage_start,
    max(azure.usage_start) as usage_end,
    max(nullif(azure.service_name, '')) as service_name,
    max(azure.instance_type) as instance_type,
    max(azure.subscription_guid) as subscription_guid,
    max(azure.subscription_name) as subscription_name,
    max(nullif(azure.resource_location, '')) as resource_location,
    max(azure.unit_of_measure) as unit_of_measure,
    max(cast(azure.usage_quantity as decimal(24,9))) as usage_quantity,
    max(azure.currency) as currency,
    max(cast(azure.pretax_cost as decimal(24,9))) as pretax_cost,
    max(cast(azure.pretax_cost as decimal(24,9))) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
    sum(ocp.pod_effective_usage_cpu_core_hours) as pod_effective_usage_cpu_core_hours,
    sum(ocp.pod_effective_usage_memory_gigabyte_hours) as pod_effective_usage_memory_gigabyte_hours,
    max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
    max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
    ocp.pod_labels,
    ocp.volume_labels,
    max(azure.tags) as tags,
    max(azure.resource_id_matched) as resource_id_matched,
    max(ocp.cost_category_id) as cost_category_id,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON (azure.usage_start = ocp.usage_start)
        AND (
                (replace(lower(azure.resource_id), '_osdisk', '') = lower(ocp.node) AND ocp.data_source = 'Pod')
                OR (strpos(azure.resource_id, ocp.persistentvolume) > 0 AND ocp.data_source = 'Storage')
            )
        AND ocp.source = azure.ocp_source
    LEFT JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_disk_capacities_temp as disk_cap
        ON azure.resource_id = disk_cap.resource_id
        AND disk_cap.year = azure.year
        AND disk_cap.month = azure.month
        AND disk_cap.ocp_source = azure.ocp_source
    WHERE ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
        AND azure.resource_id_matched = True
        -- Filter out Node Network Costs because they cannot be tied to namespace level
        AND azure.data_transfer_direction IS NULL
        AND azure.ocp_source = {{ocp_provider_uuid}}
        AND azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND disk_cap.resource_id is NULL -- exclude any resource used in disk capacity calculations
    GROUP BY azure.row_uuid, ocp.namespace, ocp.data_source, ocp.pod_labels, ocp.volume_labels
;

-- Tag matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (
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
    service_name,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    pod_labels,
    volume_labels,
    tags,
    matched_tag,
    resource_id_matched,
    cost_category_id,
    source,
    ocp_source,
    year,
    month
)
SELECT azure.row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    ocp.data_source,
    ocp.namespace,
    max(ocp.node) as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(azure.resource_id) as resource_id,
    max(azure.usage_start) as usage_start,
    max(azure.usage_start) as usage_end,
    max(nullif(azure.service_name, '')) as service_name,
    max(azure.instance_type) as instance_type,
    max(azure.subscription_guid) as subscription_guid,
    max(subscription_name) as subscription_name,
    max(nullif(azure.resource_location, '')) as resource_location,
    max(azure.unit_of_measure) as unit_of_measure,
    max(cast(azure.usage_quantity as decimal(24,9))) as usage_quantity,
    max(azure.currency) as currency,
    max(cast(azure.pretax_cost as decimal(24,9))) as pretax_cost,
    max(cast(azure.pretax_cost as decimal(24,9))) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
    max(ocp.pod_labels) as pod_labels,
    max(ocp.volume_labels) as volume_labels,
    max(azure.tags) as tags,
    max(azure.matched_tag) as matched_tag,
    FALSE as resource_id_matched,
    max(ocp.cost_category_id) as cost_category_id,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON azure.usage_start = ocp.usage_start
        AND (
                json_query(azure.tags, 'strict $.openshift_project' OMIT QUOTES) = ocp.namespace
                OR json_query(azure.tags, 'strict $.openshift_node' OMIT QUOTES) = ocp.node
                OR json_query(azure.tags, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_alias
                OR json_query(azure.tags, 'strict $.openshift_cluster' OMIT QUOTES) = ocp.cluster_id
                OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(ocp.pod_labels, replace(x, ' ')) != 0))
                OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(ocp.volume_labels, replace(x, ' ')) != 0))
            )
        AND namespace != 'Worker unallocated'
        AND namespace != 'Platform unallocated'
        AND namespace != 'Storage unattributed'
        AND namespace != 'Network unattributed'
        AND azure.ocp_source = ocp.source
    WHERE ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND azure.ocp_source = {{ocp_provider_uuid}}
        AND azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND azure.matched_tag != ''
        AND azure.resource_id_matched = False
    GROUP BY azure.row_uuid, ocp.namespace, ocp.data_source
;

{%- if distribution == 'cpu' -%}
{%- set pod_column = 'pod_effective_usage_cpu_core_hours' -%}
{%- set node_column = 'node_capacity_cpu_core_hours' -%}
{%- else -%}
{%- set pod_column = 'pod_effective_usage_memory_gigabyte_hours' -%}
{%- set node_column = 'node_capacity_memory_gigabyte_hours' -%}
{%- endif -%}
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary (
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
    service_name,
    data_transfer_direction,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    tags,
    resource_id_matched,
    matched_tag,
    cost_category_id,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_cluster_counts AS (
    -- Count distinct clusters matching each Azure resource for tag-matched resources
    SELECT azure.row_uuid,
        count(DISTINCT azure.ocp_source) as cluster_count
    FROM hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp AS azure
    WHERE azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND azure.resource_id_matched = FALSE
        AND azure.matched_tag IS NOT NULL
        AND azure.matched_tag != ''
    GROUP BY azure.row_uuid
),
cte_rankings AS (
    SELECT pds.row_uuid,
        count(*) as row_uuid_count,
        COALESCE(ccc.cluster_count, 1) as cluster_count
    FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp AS pds
    LEFT JOIN cte_cluster_counts AS ccc
        ON pds.row_uuid = ccc.row_uuid
    GROUP BY pds.row_uuid, ccc.cluster_count
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
    service_name,
    NULL as data_transfer_direction,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    -- For tag-matched resources, split cost across clusters; for resource_id-matched, only split within cluster
    CASE WHEN pds.resource_id_matched = FALSE
        THEN usage_quantity / (r.row_uuid_count * r.cluster_count)
        ELSE usage_quantity / r.row_uuid_count
    END as usage_quantity,
    currency,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost
        WHEN resource_id_matched = FALSE
        THEN pretax_cost / (r.row_uuid_count * r.cluster_count)
        ELSE pretax_cost / r.row_uuid_count
    END as pretax_cost,
    CASE WHEN resource_id_matched = TRUE AND data_source = 'Pod'
        THEN ({{pod_column | sqlsafe}} / {{node_column | sqlsafe}}) * pretax_cost * cast({{markup}} as decimal(24,9))
        WHEN resource_id_matched = FALSE
        THEN pretax_cost / (r.row_uuid_count * r.cluster_count) * cast({{markup}} as decimal(24,9))
        ELSE pretax_cost / r.row_uuid_count * cast({{markup}} as decimal(24,9))
    END as markup_cost,
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
    pds.resource_id_matched as resource_id_matched,
    pds.matched_tag as matched_tag,
    cost_category_id,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    pds.year as year,
    pds.month as month,
    cast(day(usage_start) as varchar) as day
FROM hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary_temp AS pds
JOIN cte_rankings as r
    ON pds.row_uuid = r.row_uuid
WHERE
    pds.ocp_source = {{ocp_provider_uuid}}
    AND pds.year = {{year}}
    AND pds.month = {{month}}
    AND pds.source = {{cloud_provider_uuid}}
;

-- Network costs are currently not mapped to pod metrics
-- and are filtered out of the above SQL since that is grouped by namespace
-- and costs are split out by pod metrics, this puts all network costs per node
-- into a "Network unattributed" project with no cost split and one record per
-- data direction
INSERT INTO hive.{{schema | sqlsafe}}.managed_reporting_ocpazurecostlineitem_project_daily_summary (
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
    service_name,
    data_transfer_direction,
    instance_type,
    subscription_guid,
    subscription_name,
    resource_location,
    unit_of_measure,
    usage_quantity,
    currency,
    pretax_cost,
    markup_cost,
    tags,
    source,
    ocp_source,
    year,
    month,
    day
)
SELECT azure.row_uuid as row_uuid,
    max(ocp.cluster_id) as cluster_id,
    max(ocp.cluster_alias) as cluster_alias,
    max(ocp.data_source) as data_source,
    'Network unattributed' as namespace,
    ocp.node as node,
    max(nullif(ocp.persistentvolumeclaim, '')) as persistentvolumeclaim,
    max(nullif(ocp.persistentvolume, '')) as persistentvolume,
    max(nullif(ocp.storageclass, '')) as storageclass,
    max(azure.resource_id) as resource_id,
    max(azure.usage_start) as usage_start,
    max(azure.usage_start) as usage_end,
    max(nullif(azure.service_name, '')) as service_name,
    max(data_transfer_direction) as data_transfer_direction,
    max(azure.instance_type) as instance_type,
    max(azure.subscription_guid) as subscription_guid,
    max(azure.subscription_name) as subscription_name,
    max(nullif(azure.resource_location, '')) as resource_location,
    max(azure.unit_of_measure) as unit_of_measure,
    max(cast(azure.usage_quantity as decimal(24,9))) as usage_quantity,
    max(azure.currency) as currency,
    max(cast(azure.pretax_cost as decimal(24,9))) as pretax_cost,
    max(cast(azure.pretax_cost as decimal(24,9))) * cast({{markup}} as decimal(24,9)) as markup_cost, -- pretax_cost x markup = markup_cost
    max(azure.tags) as tags,
    {{cloud_provider_uuid}} as source,
    {{ocp_provider_uuid}} as ocp_source,
    max(azure.year) as year,
    max(azure.month) as month,
    cast(day(max(azure.usage_start)) as varchar) as day
    FROM hive.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
    JOIN hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp as azure
        ON azure.usage_start = ocp.usage_start
        AND (azure.resource_id = ocp.node AND ocp.data_source = 'Pod')
        AND azure.ocp_source = ocp.source
    WHERE ocp.source = {{ocp_provider_uuid}}
        AND ocp.year = {{year}}
        AND lpad(ocp.month, 2, '0') = {{month}} -- Zero pad the month when fewer than 2 characters
        AND ocp.usage_start >= {{start_date}}
        AND ocp.usage_start < date_add('day', 1, {{end_date}})
        AND (ocp.resource_id IS NOT NULL AND ocp.resource_id != '')
        -- Filter for Node Network Costs to tie them to the Network unattributed project
        AND azure.data_transfer_direction IS NOT NULL
        AND azure.data_transfer_direction != ''
        AND azure.ocp_source = {{ocp_provider_uuid}}
        AND azure.source = {{cloud_provider_uuid}}
        AND azure.year = {{year}}
        AND azure.month = {{month}}
        AND azure.resource_id_matched = True
    GROUP BY azure.row_uuid, ocp.node
;
