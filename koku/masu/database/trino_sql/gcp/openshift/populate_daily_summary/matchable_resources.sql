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
    SELECT DISTINCT resource_name
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
    JOIN cte_usage_date_partitions AS ym ON gcp.year = ym.year AND gcp.month = ym.month
    WHERE source = {{cloud_provider_uuid}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < date_add('day', 1, {{end_date}})
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
    )
