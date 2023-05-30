-- Now create our proper table if it does not exist
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
    TRUE as ocp_matched,
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

-- Will need to add in tag matching here as well






-- Needs insert statement + Andrew magic :)
-- WITH cte_openshift_topology AS (
--   SELECT max(cluster.cluster_id) as cluster_id,
--   max(cluster.cluster_alias) as cluster_alias,
--   cluster.provider_id,
--   array_agg(DISTINCT node.node) as nodes,
--   array_agg(DISTINCT node.resource_id) as node_resource_ids,
--   array_agg(DISTINCT pvc.persistent_volume) as pvs
-- FROM postgres.{{schema_name | sqlsafe}}.reporting_ocp_clusters AS cluster
--   JOIN postgres.{{schema_name | sqlsafe}}.reporting_ocp_nodes AS node
--     ON node.cluster_id = cluster.uuid
--   JOIN postgres.{{schema_name | sqlsafe}}.reporting_ocp_pvcs AS pvc
--     ON pvc.cluster_id = cluster.uuid
--   JOIN postgres.public.api_provider AS provider
--     ON cluster.provider_id = provider.uuid
--   JOIN postgres.public.api_providerinfrastructuremap AS infra
--     ON provider.infrastructure_id = infra.id
-- WHERE infra.infrastructure_type LIKE 'GCP%'
-- GROUP BY cluster.provider_id
-- )
-- SELECT gcp.*
-- FROM hive.{{schema_name | sqlsafe}}.gcp_line_items_daily AS gcp
-- JOIN cte_openshift_topology AS ocp
--   ON any_match(ocp.nodes , x -> lower(gcp.resource_name) LIKE '%' || lower(x))
--     OR any_match(ocp.pvs , x -> lower(gcp.resource_name) LIKE '%' || lower(x))
--     OR gcp.labels LIKE '%kubernetes-io-cluster-' || ocp.cluster_id
--     OR gcp.labels LIKE '%kubernetes-io-cluster-' || ocp.cluster_alias
