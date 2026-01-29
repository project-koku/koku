/*
 * Process OCP Usage Data Processing SQL
 * PostgreSQL version for self-hosted/on-prem deployment
 *
 * Note: The staging table (reporting_ocpusagelineitem_daily_summary_staging)
 * is created by Django migrations. See self_hosted_models.py.
 */

-- Helper function to filter JSON by allowed keys (replaces Trino's map_filter)
CREATE OR REPLACE FUNCTION {{schema | sqlsafe}}.filter_json_by_keys(input_json text, allowed_keys text[])
RETURNS text AS $$
    SELECT json_object_agg(key, value)::text
    FROM jsonb_each_text(input_json::jsonb)
    WHERE key = ANY(allowed_keys)
$$ LANGUAGE sql IMMUTABLE;

-- First INSERT: Pod and Storage usage aggregation
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    infrastructure_usage_cost,
    csi_volume_handle,
    cost_category_id,
    source,
    year,
    month,
    day
)
WITH cte_pg_enabled_keys as (
    SELECT array['vm_kubevirt_io_name'] || array_agg(key ORDER BY key) as keys
    FROM {{schema | sqlsafe}}.reporting_enabledtagkeys
    WHERE enabled = true
    AND provider_type = 'OCP'
),
cte_ocp_node_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.node,
        {{schema | sqlsafe}}.filter_json_by_keys(nli.node_labels, pek.keys)::jsonb as node_labels
    FROM {{schema | sqlsafe}}.openshift_node_labels_line_items_daily AS nli
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= {{start_date}}
       AND nli.interval_start < {{end_date}} + INTERVAL '1 day'
    GROUP BY date(nli.interval_start),
        nli.node,
        3
),
cte_ocp_namespace_label_line_item_daily AS (
    SELECT date(nli.interval_start) as usage_start,
        nli.namespace,
        {{schema | sqlsafe}}.filter_json_by_keys(nli.namespace_labels, pek.keys)::jsonb as namespace_labels
    FROM {{schema | sqlsafe}}.openshift_namespace_labels_line_items_daily AS nli
    CROSS JOIN cte_pg_enabled_keys AS pek
    WHERE nli.source = {{source}}
       AND nli.year = {{year}}
       AND nli.month = {{month}}
       AND nli.interval_start >= {{start_date}}
       AND nli.interval_start < {{end_date}} + INTERVAL '1 day'
    GROUP BY date(nli.interval_start),
        nli.namespace,
        3
),
cte_ocp_node_capacity AS (
    SELECT date(nc.interval_start) as usage_start,
        nc.node,
        sum(nc.node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
        sum(nc.node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds
    FROM (
        SELECT li.interval_start,
            li.node,
            max(li.node_capacity_cpu_core_seconds) as node_capacity_cpu_core_seconds,
            max(li.node_capacity_memory_byte_seconds) as node_capacity_memory_byte_seconds
        FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items AS li
        WHERE li.source = {{source}}
            AND li.year = {{year}}
            AND li.month = {{month}}
            AND li.interval_start >= {{start_date}}
            AND li.interval_start < {{end_date}} + INTERVAL '1 day'
        GROUP BY li.interval_start,
            li.node
    ) as nc
    GROUP BY date(nc.interval_start),
        nc.node
),
cte_ocp_cluster_capacity AS (
    SELECT nc.usage_start,
        sum(nc.node_capacity_cpu_core_seconds) as cluster_capacity_cpu_core_seconds,
        sum(nc.node_capacity_memory_byte_seconds) as cluster_capacity_memory_byte_seconds
    FROM cte_ocp_node_capacity AS nc
    GROUP BY nc.usage_start
)
{% if storage_exists %}
,
-- Determine which node a PVC is running on
cte_volume_nodes AS (
    SELECT date(sli.interval_start) as usage_start,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.pod,
        sli.namespace,
        uli.node,
        uli.resource_id
    FROM {{schema | sqlsafe}}.openshift_storage_usage_line_items_daily as sli
    JOIN {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as uli
        ON uli.source = sli.source
            AND uli.namespace = sli.namespace
            AND uli.pod = sli.pod
            AND date(uli.interval_start) = date(sli.interval_start)
     WHERE sli.source = {{source}}
        AND sli.year = {{year}}
        AND sli.month = {{month}}
        AND sli.interval_start >= {{start_date}}
        AND sli.interval_start < {{end_date}} + INTERVAL '1 day'
        AND uli.source = {{source}}
        AND uli.year = {{year}}
        AND uli.month = {{month}}
     GROUP BY date(sli.interval_start),
          sli.persistentvolumeclaim,
          sli.persistentvolume,
          sli.pod,
          sli.namespace,
          uli.node,
          uli.resource_id
),
cte_shared_volume_node_count AS (
    SELECT usage_start,
        persistentvolume,
        count(DISTINCT node) as node_count
    FROM cte_volume_nodes
    GROUP BY usage_start,
        persistentvolume
)
{% endif %}

/*
 * ====================================
 *            POD
 * ====================================
 */
SELECT null as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Pod' as data_source,
    pua.usage_start,
    pua.usage_start as usage_end,
    pua.namespace,
    pua.node,
    pua.resource_id,
    pua.pod_labels::text as pod_labels,
    pua.pod_usage_cpu_core_hours,
    pua.pod_request_cpu_core_hours,
    pua.pod_effective_usage_cpu_core_hours,
    pua.pod_limit_cpu_core_hours,
    pua.pod_usage_memory_gigabyte_hours,
    pua.pod_request_memory_gigabyte_hours,
    pua.pod_effective_usage_memory_gigabyte_hours,
    pua.pod_limit_memory_gigabyte_hours,
    pua.node_capacity_cpu_cores,
    pua.node_capacity_cpu_core_hours,
    pua.node_capacity_memory_gigabytes,
    pua.node_capacity_memory_gigabyte_hours,
    pua.cluster_capacity_cpu_core_hours,
    pua.cluster_capacity_memory_gigabyte_hours,
    NULL as persistentvolumeclaim,
    NULL as persistentvolume,
    NULL as storageclass,
    NULL as volume_labels,
    NULL as persistentvolumeclaim_capacity_gigabyte,
    NULL as persistentvolumeclaim_capacity_gigabyte_months,
    NULL as volume_request_storage_gigabyte_months,
    NULL as persistentvolumeclaim_usage_gigabyte_months,
    pua.source_uuid,
    '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost,
    NULL as csi_volume_handle,
    pua.cost_category_id,
    {{source}} as source,
    EXTRACT(YEAR FROM pua.usage_start)::text as year,
    EXTRACT(MONTH FROM pua.usage_start)::text as month,
    EXTRACT(DAY FROM pua.usage_start)::text as day
FROM (
    SELECT date(li.interval_start) as usage_start,
        li.namespace,
        li.node,
        max(cat_ns.cost_category_id) as cost_category_id,
        li.source as source_uuid,
        COALESCE(
            COALESCE(nli.node_labels, '{}'::jsonb) ||
            COALESCE(nsli.namespace_labels, '{}'::jsonb) ||
            {{schema | sqlsafe}}.filter_json_by_keys(li.pod_labels, pek.keys)::jsonb,
            '{}'::jsonb
        ) as pod_labels,
        max(li.resource_id) as resource_id,
        sum(li.pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours,
        sum(li.pod_request_cpu_core_seconds) / 3600.0  as pod_request_cpu_core_hours,
        sum(coalesce(li.pod_effective_usage_cpu_core_seconds, greatest(li.pod_usage_cpu_core_seconds, li.pod_request_cpu_core_seconds))) / 3600.0  as pod_effective_usage_cpu_core_hours,
        sum(li.pod_limit_cpu_core_seconds) / 3600.0 as pod_limit_cpu_core_hours,
        sum(li.pod_usage_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_usage_memory_gigabyte_hours,
        sum(li.pod_request_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_request_memory_gigabyte_hours,
        sum(coalesce(li.pod_effective_usage_memory_byte_seconds, greatest(pod_usage_memory_byte_seconds, pod_request_memory_byte_seconds))) / 3600.0 * power(2, -30) as pod_effective_usage_memory_gigabyte_hours,
        sum(li.pod_limit_memory_byte_seconds) / 3600.0 * power(2, -30) as pod_limit_memory_gigabyte_hours,
        max(li.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        COALESCE(max(nc.node_capacity_cpu_core_seconds), 0) / 3600.0 as node_capacity_cpu_core_hours,
        max(li.node_capacity_memory_bytes) * power(2, -30) as node_capacity_memory_gigabytes,
        COALESCE(max(nc.node_capacity_memory_byte_seconds), 0) / 3600.0 * power(2, -30) as node_capacity_memory_gigabyte_hours,
        COALESCE(max(cc.cluster_capacity_cpu_core_seconds), 0) / 3600.0 as cluster_capacity_cpu_core_hours,
        COALESCE(max(cc.cluster_capacity_memory_byte_seconds), 0) / 3600.0 * power(2, -30) as cluster_capacity_memory_gigabyte_hours
    FROM {{schema | sqlsafe}}.openshift_pod_usage_line_items_daily as li
    CROSS JOIN cte_pg_enabled_keys AS pek
    LEFT JOIN cte_ocp_node_label_line_item_daily as nli
        ON nli.node = li.node
            AND nli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
        ON nsli.namespace = li.namespace
            AND nsli.usage_start = date(li.interval_start)
    LEFT JOIN cte_ocp_node_capacity as nc
        ON nc.usage_start = date(li.interval_start)
            AND nc.node = li.node
    LEFT JOIN cte_ocp_cluster_capacity as cc
        ON cc.usage_start = date(li.interval_start)
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON li.namespace LIKE cat_ns.namespace
    WHERE li.source = {{source}}
        AND li.year = {{year}}
        AND li.month = {{month}}
        AND li.interval_start >= {{start_date}}
        AND li.interval_start < {{end_date}} + INTERVAL '1 day'
        AND li.node != ''
    GROUP BY date(li.interval_start),
        li.namespace,
        li.node,
        li.source,
        6  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE pod_labels EXPRESSION */
            /* The pod_labels expression was too complex for PostgreSQL to use */
) as pua

{% if storage_exists %}

UNION

/*
 * ====================================
 *            STORAGE
 * ====================================
 */
SELECT null as uuid,
    {{report_period_id}} as report_period_id,
    {{cluster_id}} as cluster_id,
    {{cluster_alias}} as cluster_alias,
    'Storage' as data_source,
    sua.usage_start,
    sua.usage_start as usage_end,
    sua.namespace,
    sua.node,
    sua.resource_id,
    NULL as pod_labels,
    NULL as pod_usage_cpu_core_hours,
    NULL as pod_request_cpu_core_hours,
    NULL as pod_effective_usage_cpu_core_hours,
    NULL as pod_limit_cpu_core_hours,
    NULL as pod_usage_memory_gigabyte_hours,
    NULL as pod_request_memory_gigabyte_hours,
    NULL as pod_effective_usage_memory_gigabyte_hours,
    NULL as pod_limit_memory_gigabyte_hours,
    NULL as node_capacity_cpu_cores,
    NULL as node_capacity_cpu_core_hours,
    NULL as node_capacity_memory_gigabytes,
    NULL as node_capacity_memory_gigabyte_hours,
    NULL as cluster_capacity_cpu_core_hours,
    NULL as cluster_capacity_memory_gigabyte_hours,
    sua.persistentvolumeclaim,
    sua.persistentvolume,
    sua.storageclass,
    sua.volume_labels::text as volume_labels,
    (sua.persistentvolumeclaim_capacity_bytes *
        power(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
    (sua.persistentvolumeclaim_capacity_byte_seconds /
        (
            86400 *
            EXTRACT(DAY FROM (DATE_TRUNC('month', date(sua.usage_start)) + INTERVAL '1 month - 1 day'))::integer
        ) *
        power(2, -30)) as persistentvolumeclaim_capacity_gigabyte_months,
    (sua.volume_request_storage_byte_seconds /
        (
            86400 *
            EXTRACT(DAY FROM (DATE_TRUNC('month', date(sua.usage_start)) + INTERVAL '1 month - 1 day'))::integer
        ) *
        power(2, -30)) as volume_request_storage_gigabyte_months,
    (sua.persistentvolumeclaim_usage_byte_seconds /
        (
            86400 *
            EXTRACT(DAY FROM (DATE_TRUNC('month', date(sua.usage_start)) + INTERVAL '1 month - 1 day'))::integer
        ) *
        power(2, -30)) as persistentvolumeclaim_usage_gigabyte_months,
    sua.source_uuid,
    '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}' as infrastructure_usage_cost,
    sua.csi_volume_handle,
    sua.cost_category_id,
    {{source}} as source,
    EXTRACT(YEAR FROM sua.usage_start)::text as year,
    EXTRACT(MONTH FROM sua.usage_start)::text as month,
    EXTRACT(DAY FROM sua.usage_start)::text as day
FROM (
    SELECT sli.namespace,
        vn.node,
        vn.resource_id,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.storageclass,
        date(sli.interval_start) as usage_start,
        COALESCE(
            COALESCE(nli.node_labels, '{}'::jsonb) ||
            COALESCE(nsli.namespace_labels, '{}'::jsonb) ||
            {{schema | sqlsafe}}.filter_json_by_keys(sli.persistentvolume_labels, pek.keys)::jsonb ||
            {{schema | sqlsafe}}.filter_json_by_keys(sli.persistentvolumeclaim_labels, pek.keys)::jsonb,
            '{}'::jsonb
        ) as volume_labels,
        sli.source as source_uuid,
        sli.csi_volume_handle as csi_volume_handle,
        max(cat_ns.cost_category_id) as cost_category_id,
        max(sli.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
        sum(sli.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
        -- Divide volume usage and requests by the number of nodes that volume is mounted on
        sum(sli.volume_request_storage_byte_seconds) / COALESCE(max(nc.node_count), 1) as volume_request_storage_byte_seconds,
        sum(sli.persistentvolumeclaim_usage_byte_seconds) / COALESCE(max(nc.node_count), 1) as persistentvolumeclaim_usage_byte_seconds
    FROM {{schema | sqlsafe}}.openshift_storage_usage_line_items_daily sli
    CROSS JOIN cte_pg_enabled_keys AS pek
    LEFT JOIN cte_volume_nodes as vn
        ON vn.usage_start = date(sli.interval_start)
            AND vn.persistentvolumeclaim = sli.persistentvolumeclaim
            AND vn.pod = sli.pod
            AND vn.namespace = sli.namespace
    LEFT JOIN cte_shared_volume_node_count as nc
        ON nc.usage_start = date(sli.interval_start)
            AND nc.persistentvolume = sli.persistentvolume
    LEFT JOIN cte_ocp_node_label_line_item_daily as nli
        ON nli.node = vn.node
            AND nli.usage_start = vn.usage_start
    LEFT JOIN cte_ocp_namespace_label_line_item_daily as nsli
        ON nsli.namespace = sli.namespace
            AND nsli.usage_start = date(sli.interval_start)
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
        ON sli.namespace LIKE cat_ns.namespace
    WHERE sli.source = {{source}}
        AND sli.year = {{year}}
        AND sli.month = {{month}}
        AND sli.interval_start >= {{start_date}}
        AND sli.interval_start < {{end_date}} + INTERVAL '1 day'
    GROUP BY sli.namespace,
        vn.node,
        vn.resource_id,
        sli.persistentvolumeclaim,
        sli.persistentvolume,
        sli.storageclass,
        sli.csi_volume_handle,
        date(sli.interval_start),
        8,  /* THIS ORDINAL MUST BE KEPT IN SYNC WITH THE volume_labels EXPRESSION */
            /* The volume_labels expression was too complex for PostgreSQL to use */
        sli.source
) as sua

{% endif %}

RETURNING 1;

/*
 * ====================================
 *        UNALLOCATED CAPACITY
 * ====================================
Developer Note: Add these to make it easier to verify
What was selected from unallocated capacity.
AND lids.namespace != 'Platform unallocated'
AND lids.namespace != 'Worker unallocated'
 */
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    data_source,
    source_uuid,
    cost_category_id,
    source,
    year,
    month,
    day
)
WITH cte_node_role AS (
    SELECT
        max(node_role) AS node_role,
        node,
        resource_id
    FROM {{schema | sqlsafe}}.reporting_ocp_nodes
    GROUP BY node, resource_id
),
cte_unallocated_capacity AS (
    SELECT
        NULL as uuid,
        {{report_period_id}} as report_period_id,
        {{cluster_id}} as cluster_id,
        {{cluster_alias}} as cluster_alias,
        max(lids.usage_start) as usage_start,
        max(lids.usage_end) as usage_end,
        CASE max(nodes.node_role)
            WHEN 'master' THEN 'Platform unallocated'
            WHEN 'infra' THEN 'Platform unallocated'
            WHEN 'worker' THEN 'Worker unallocated'
        END as namespace,
        lids.node,
        max(lids.resource_id) as resource_id,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_usage_cpu_core_hours)) as pod_usage_cpu_core_hours,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_request_cpu_core_hours)) as pod_request_cpu_core_hours,
        (max(lids.node_capacity_cpu_core_hours) - sum(lids.pod_effective_usage_cpu_core_hours)) as pod_effective_usage_cpu_core_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_usage_memory_gigabyte_hours)) as pod_usage_memory_gigabyte_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_request_memory_gigabyte_hours)) as pod_request_memory_gigabyte_hours,
        (max(lids.node_capacity_memory_gigabyte_hours) - sum(lids.pod_effective_usage_memory_gigabyte_hours)) as pod_effective_usage_memory_gigabyte_hours,
        max(lids.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(lids.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(lids.node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(lids.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(lids.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(lids.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        max(lids.data_source) as data_source,
        lids.source_uuid,
        {{source}} as source,
        EXTRACT(YEAR FROM lids.usage_start)::text as year,
        EXTRACT(MONTH FROM lids.usage_start)::text as month,
        EXTRACT(DAY FROM lids.usage_start)::text as day
    FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging as lids
    LEFT JOIN cte_node_role AS nodes
        ON lids.node = nodes.node
        AND lids.resource_id = nodes.resource_id
    WHERE lids.source = {{source}}
        AND lids.year = {{year}}
        AND lpad(lids.month, 2, '0') = {{month}}
        AND lids.usage_start >= {{start_date}}
        AND lids.usage_start < {{end_date}} + INTERVAL '1 day'
        AND lids.namespace != 'Platform unallocated'
        AND lids.namespace != 'Worker unallocated'
        AND lids.namespace != 'Network unattributed'
        AND lids.namespace != 'Storage unattributed'
        AND lids.node IS NOT NULL
        AND lids.data_source = 'Pod'
    GROUP BY lids.node, lids.usage_start, lids.source_uuid
)
SELECT
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    uc.namespace,
    node,
    resource_id,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    data_source,
    source_uuid,
    cat_ns.cost_category_id as cost_category_id,
    source,
    year,
    month,
    day
FROM cte_unallocated_capacity AS uc
LEFT JOIN {{schema | sqlsafe}}.reporting_ocp_cost_category_namespace AS cat_ns
    ON uc.namespace LIKE cat_ns.namespace
RETURNING 1;

INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels,
    all_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid,
    infrastructure_usage_cost,
    cost_category_id
)
SELECT uuid_generate_v4(),
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    usage_start,
    usage_end,
    namespace,
    node,
    resource_id,
    pod_labels::jsonb,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_effective_usage_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_effective_usage_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    volume_labels::jsonb,
    COALESCE(pod_labels::jsonb, '{}'::jsonb) || COALESCE(volume_labels::jsonb, '{}'::jsonb) as all_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid::uuid,
    infrastructure_usage_cost::jsonb,
    cost_category_id
FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary_staging AS lids
WHERE lids.source = {{source}}
    AND lids.year = {{year}}
    AND lpad(lids.month, 2, '0') = {{month}}
    AND lids.day IN {{days | inclause}}
RETURNING 1;
