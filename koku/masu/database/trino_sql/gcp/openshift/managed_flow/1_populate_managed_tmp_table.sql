DELETE FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp
WHERE ocp_source = {{ocp_source_uuid}}
AND source = {{cloud_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

-- Direct resource matching
INSERT INTO hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_openshift_daily_temp (
    row_uuid,
    invoice_month,
    billing_account_id,
    project_id,
    usage_start_time,
    service_id,
    sku_id,
    system_labels,
    labels,
    cost_type,
    location_region,
    resource_name,
    project_name,
    service_description,
    sku_description,
    usage_pricing_unit,
    usage_amount_in_pricing_units,
    currency,
    cost,
    daily_credits,
    resource_global_name,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_gcp_resource_names AS (
    SELECT DISTINCT resource_name
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_uuid_temp
    WHERE source = {{cloud_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
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
        )
),
cte_agg_tags AS (
    SELECT array_agg(cte_tag_matches.matched_tag) as matched_tags from (
        SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)
    ) as cte_tag_matches
)
SELECT gcp.row_uuid,
    gcp.invoice_month,
    gcp.billing_account_id,
    gcp.project_id,
    gcp.usage_start_time,
    gcp.service_id,
    gcp.sku_id,
    gcp.system_labels,
    gcp.labels,
    gcp.cost_type,
    gcp.location_region,
    gcp.resource_name,
    gcp.project_name,
    gcp.service_description,
    gcp.sku_description,
    gcp.usage_pricing_unit,
    gcp.usage_amount_in_pricing_units,
    gcp.currency,
    gcp.cost,
    gcp.daily_credits,
    gcp.resource_global_name,
    CASE WHEN resource_names.resource_name IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(labels, x ) != 0), ',') as matched_tag,
    gcp.source as source,
    {{ocp_source_uuid}} as ocp_source,
    gcp.year,
    gcp.month,
    cast(day(gcp.usage_start_time) as varchar) as day
FROM hive.{{trino_schema_prefix | sqlsafe}}{{schema | sqlsafe}}.managed_gcp_uuid_temp AS gcp
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON gcp.resource_name = resource_names.resource_name
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(labels, x) != 0)
    AND resource_names.resource_name IS NULL
WHERE gcp.source = {{cloud_provider_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month= {{month}}
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
    AND (resource_names.resource_name IS NOT NULL OR tag_matches.matched_tags IS NOT NULL);
