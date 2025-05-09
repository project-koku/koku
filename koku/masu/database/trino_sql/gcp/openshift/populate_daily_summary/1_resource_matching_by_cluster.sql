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
WITH cte_gcp_resource_names AS (
    SELECT DISTINCT resource_name
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily
    WHERE source = {{cloud_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
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
    gcp.year,
    gcp.month,
    cast(day(gcp.usage_start_time) as varchar) as day
FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
CROSS JOIN cte_enabled_tag_keys as etk
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
