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
    cost_Type varchar,
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
    ocp_source_uuid varchar,
    ocp_matched boolean,
    matched_tag varchar,
    uuid varchar,
    gcp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['gcp_source', 'ocp_source_uuid', 'year', 'month', 'day'])
;





-- Needs insert statement + Andrew magic :)
WITH cte_openshift_topology AS (
  SELECT max(cluster.cluster_id) as cluster_id,
  max(cluster.cluster_alias) as cluster_alias,
  cluster.provider_id,
  array_agg(DISTINCT node.node) as nodes,
  array_agg(DISTINCT node.resource_id) as node_resource_ids,
  array_agg(DISTINCT pvc.persistent_volume) as pvs
FROM postgres.{{schema_name | sqlsafe}}.reporting_ocp_clusters AS cluster
  JOIN postgres.{{schema_name | sqlsafe}}.reporting_ocp_nodes AS node
    ON node.cluster_id = cluster.uuid
  JOIN postgres.{{schema_name | sqlsafe}}.reporting_ocp_pvcs AS pvc
    ON pvc.cluster_id = cluster.uuid
  JOIN postgres.public.api_provider AS provider
    ON cluster.provider_id = provider.uuid
  JOIN postgres.public.api_providerinfrastructuremap AS infra
    ON provider.infrastructure_id = infra.id
WHERE infra.infrastructure_type LIKE 'GCP%'
GROUP BY cluster.provider_id
)
SELECT gcp.*
FROM hive.{{schema_name | sqlsafe}}.gcp_line_items_daily AS gcp
JOIN cte_openshift_topology AS ocp
  ON any_match(ocp.nodes , x -> lower(gcp.resource_name) LIKE '%' || lower(x))
    OR any_match(ocp.pvs , x -> lower(gcp.resource_name) LIKE '%' || lower(x))
    OR gcp.labels LIKE '%kubernetes-io-cluster-' || ocp.cluster_id
    OR gcp.labels LIKE '%kubernetes-io-cluster-' || ocp.cluster_alias
