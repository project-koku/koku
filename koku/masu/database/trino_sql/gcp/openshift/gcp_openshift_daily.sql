CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.gcp_openshift_daily
(
    invoice_month varchar,
    billing_account_id varchar,
    project_id varchar,
    usage_start_time timestamp,
    service_id varchar,
    sku_id varchar,
    system_labels varchar,
    labels varchar,
    cost_type varchar,
    location_region varchar,
    resource_name varchar,
    project_name varchar,
    service_description varchar,
    sku_description varchar,
    usage_pricing_unit varchar,
    usage_amount_in_pricing_units double,
    currency varchar,
    cost double,
    daily_credits double,
    resource_global_name varchar,
    ocp_matched boolean,
    matched_tag varchar,
    gcp_source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['gcp_source', 'ocp_source', 'year', 'month', 'day'])
;

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.gcp_openshift_daily (
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
    ocp_matched,
    matched_tag,
    gcp_source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_gcp_resource_names AS (
    SELECT DISTINCT resource_name
    FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily
    WHERE source = {{gcp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND usage_start_time >= {{start_date}}
        AND usage_start_time < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_node_labels_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
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
        ON strpos(resource_names.resource_name, nodes.node) != 0

    UNION

    SELECT resource_names.resource_name
    FROM cte_gcp_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON strpos(resource_names.resource_name, volumes.persistentvolume) != 0
),
cte_tag_matches AS (
  SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)

  UNION

  SELECT * FROM unnest(ARRAY['openshift_cluster', 'openshift_node', 'openshift_project']) as t(matched_tag)
)
SELECT gcp.invoice_month,
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
    END as ocp_matched,
    tag_matches.matched_tag as matched_tag,
    gcp.source,
    {{ocp_source_uuid}} as ocp_source,
    gcp.year,
    gcp.month,
    cast(day(gcp.usage_start_time) as varchar) as day
FROM hive.{{schema | sqlsafe}}.gcp_line_items_daily AS gcp
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON gcp.resource_name = resource_names.resource_name
LEFT JOIN cte_tag_matches AS tag_matches
    ON strpos(gcp.labels, tag_matches.matched_tag) != 0
WHERE gcp.source = {{gcp_source_uuid}}
    AND gcp.year = {{year}}
    AND gcp.month= {{month}}
    AND gcp.usage_start_time >= {{start_date}}
    AND gcp.usage_start_time < date_add('day', 1, {{end_date}})
    AND (resource_names.resource_name IS NOT NULL OR tag_matches.matched_tag IS NOT NULL)
