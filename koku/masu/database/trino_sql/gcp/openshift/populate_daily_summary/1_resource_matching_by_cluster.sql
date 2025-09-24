DELETE FROM hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp
WHERE ocp_source = {{ocp_provider_uuid}}
AND source = {{cloud_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp (
    row_uuid,
    invoice_month,
    account_id,
    project_id,
    usage_start,
    data_transfer_direction,
    service_id,
    sku_id,
    system_labels,
    labels,
    cost_type,
    region,
    resource_name,
    instance_type,
    project_name,
    service_description,
    service_alias,
    sku_description,
    sku_alias,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    credit_amount,
    resource_global_name,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_usage_date_partitions as (
    select
        year,
        month
    from hive.{{schema | sqlsafe}}.gcp_line_items_daily
    where usage_start_time >= {{start_date}}
    AND usage_start_time <= {{end_date}}
    AND source = {{cloud_provider_uuid}}
    AND (
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}})) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}})) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}})) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{start_date}}) - INTERVAL '1' MONTH) AS VARCHAR), 2, '0'))
        OR
        (year = CAST(EXTRACT(YEAR FROM DATE({{end_date}}) + INTERVAL '1' MONTH) AS VARCHAR) AND month = LPAD(CAST(EXTRACT(MONTH FROM DATE({{end_date}}) + INTERVAL '1' MONTH) AS VARCHAR), 2, '0'))
    )
    group by year, month
),
cte_gcp_resource_names AS (
    SELECT resource_name,
        resource_global_name
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    JOIN cte_usage_date_partitions AS ym ON gcp.year = ym.year AND gcp.month = ym.month
    WHERE source = {{cloud_provider_uuid}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < date_add('day', 1, {{end_date}})
    GROUP BY resource_name, resource_global_name
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
    SELECT resource_names.resource_name
    FROM cte_gcp_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON nodes.node != ''
        AND strpos(resource_names.resource_name, nodes.node) != 0

    UNION

    SELECT resource_names.resource_name
    FROM cte_gcp_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON (
            (volumes.persistentvolume != '' AND strpos(resource_names.resource_name, volumes.persistentvolume) != 0)
            OR (volumes.csi_volume_handle != '' AND strpos(resource_names.resource_name, volumes.csi_volume_handle) != 0)
            OR (volumes.csi_volume_handle != '' AND strpos(resource_names.resource_global_name, volumes.csi_volume_handle) != 0)
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
        AND provider_type = 'GCP'
)
SELECT gcp.row_uuid,
    gcp.invoice_month,
    gcp.billing_account_id as account_id,
    gcp.project_id,
    gcp.usage_start_time as usage_start,
    CASE
        WHEN gcp.service_description = 'Compute Engine'
            AND STRPOS(lower(sku_description), 'data transfer in') != 0
            AND resource_names.resource_name IS NOT NULL
                THEN 'IN'
        WHEN gcp.service_description = 'Compute Engine'
            AND STRPOS(lower(sku_description), 'data transfer') != 0
            AND resource_names.resource_name IS NOT NULL
                THEN 'OUT'
        ELSE NULL
    END as data_transfer_direction,
    gcp.service_id,
    nullif(gcp.sku_id, ''),
    gcp.system_labels,
    json_format(
        cast(
            map_filter(
                cast(json_parse(gcp.labels) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as labels,
    gcp.cost_type,
    gcp.location_region as region,
    gcp.resource_name,
    json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]') as instance_type,
    gcp.project_name,
    gcp.service_description,
    nullif(gcp.service_description, '') as service_alias,
    gcp.sku_description,
    nullif(gcp.sku_description, '') as sku_alias,
    gcp.usage_pricing_unit as unit,
    cast(gcp.usage_amount_in_pricing_units AS decimal(24,9)) as usage_amount,
    gcp.currency,
    cast(gcp.cost AS decimal(24,9)) as unblended_cost,
    gcp.daily_credits as credit_amount,
    gcp.resource_global_name,
    CASE WHEN resource_names.resource_name IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(labels, x ) != 0), ',') as matched_tag,
    gcp.source as source,
    {{ocp_provider_uuid}} as ocp_source,
    -- GCP has crossover data and some current year data can land in the previous year partition
    -- The year partition needs to match usage_start_year for correct ocp/gcp correlation
    CAST(FORMAT_DATETIME(usage_start_time, 'YYYY') AS VARCHAR(4)) AS year,
    -- GCP has crossover data and some current month data can land in the previous month partition
    -- The month partition needs to match usage_start_month for correct ocp/gcp correlation
    CAST(FORMAT_DATETIME(usage_start_time, 'MM') AS VARCHAR(2)) AS month,
    cast(day(gcp.usage_start_time) as varchar) as day
FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
CROSS JOIN cte_enabled_tag_keys as etk
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON gcp.resource_name = resource_names.resource_name
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(labels, x) != 0)
    AND resource_names.resource_name IS NULL
JOIN cte_usage_date_partitions AS ym ON gcp.year = ym.year AND gcp.month = ym.month
WHERE gcp.source = {{cloud_provider_uuid}}
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
    AND (resource_names.resource_name IS NOT NULL OR tag_matches.matched_tags IS NOT NULL);
