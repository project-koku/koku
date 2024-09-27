-- Now create our proper table if it does not exist
CREATE TABLE IF NOT EXISTS hive.{{schema | sqlsafe}}.managed_azure_openshift_daily
(
    accountname varchar,
    additionalinfo varchar,
    billingcurrency varchar,
    billingcurrencycode varchar,
    consumedservice varchar,
    costinbillingcurrency double,
    date timestamp(3),
    effectiveprice double,
    frequency varchar,
    isazurecrediteligible varchar,
    metercategory varchar,
    metername varchar,
    metersubcategory varchar,
    productname varchar,
    publishername varchar,
    publishertype varchar,
    quantity double,
    resourcegroup varchar,
    resourceid varchar,
    resourcelocation varchar,
    resourcetype varchar,
    servicefamily varchar,
    serviceinfo1 varchar,
    serviceinfo2 varchar,
    servicename varchar,
    servicetier varchar,
    subscriptionguid varchar,
    subscriptionid varchar,
    subscriptionname varchar,
    tags varchar,
    term varchar,
    unitofmeasure varchar,
    unitprice double,
    resource_id_matched boolean,
    matched_tag varchar,
    source varchar,
    ocp_source varchar,
    year varchar,
    month varchar,
    day varchar
) WITH(format = 'PARQUET', partitioned_by=ARRAY['source', 'ocp_source', 'year', 'month', 'day'])
;

-- Direct resource matching
INSERT INTO hive.{{schema | sqlsafe}}.managed_azure_openshift_daily (
    accountname,
    additionalinfo,
    billingcurrency,
    billingcurrencycode,
    consumedservice,
    costinbillingcurrency,
    date,
    effectiveprice,
    frequency,
    isazurecrediteligible,
    metercategory,
    metername,
    metersubcategory,
    productname,
    publishername,
    publishertype,
    quantity,
    resourcegroup,
    resourceid,
    resourcelocation,
    resourcetype,
    servicefamily,
    serviceinfo1,
    serviceinfo2,
    servicename,
    servicetier,
    subscriptionguid,
    subscriptionid,
    subscriptionname,
    tags,
    term,
    unitofmeasure,
    unitprice,
    resource_id_matched,
    matched_tag,
    source,
    ocp_source,
    year,
    month,
    day
)
WITH cte_azure_resource_names AS (
    SELECT DISTINCT resourceid
    FROM hive.{{schema | sqlsafe}}.azure_line_items
    WHERE source = {{azure_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND date >= {{start_date}}
        AND date < date_add('day', 1, {{end_date}})
),
cte_array_agg_nodes AS (
    SELECT DISTINCT node
    FROM hive.{{schema | sqlsafe}}.openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_array_agg_volumes AS (
    SELECT DISTINCT persistentvolume, csi_volume_handle
    FROM hive.{{schema | sqlsafe}}.openshift_storage_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND interval_start >= {{start_date}}
        AND interval_start < date_add('day', 1, {{end_date}})
),
cte_matchable_resource_names AS (
    SELECT resource_names.resourceid
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON strpos(resource_names.resourceid, nodes.node) != 0

    UNION

    SELECT resource_names.resourceid
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON (
            strpos(resource_names.resourceid, volumes.persistentvolume) != 0
            OR strpos(resource_names.resourceid, volumes.csi_volume_handle) != 0
        )

),
cte_cluster_info as (
    select
        format('"openshift_cluster": "%s"', json_extract_scalar(auth.credentials, '$.cluster_id')) AS cluster_id,
        format('"openshift_cluster": "%s"', provider.name) as cluster_alias
    from postgres.public.api_provider as provider
    inner join postgres.public.api_providerauthentication as auth
    ON provider.authentication_id = auth.id
    and provider.uuid = CAST({{ocp_source_uuid}} as UUID)
),
cte_tag_matches AS (
    SELECT * FROM unnest(ARRAY{{matched_tag_array | sqlsafe}}) as t(matched_tag)

    UNION

    SELECT cluster_alias from cte_cluster_info

    UNION

    SELECT cluster_id from cte_cluster_info

    UNION

    SELECT format('"openshift_node": "%s"', node) AS matched_tag  from cte_array_agg_nodes

    UNION

    SELECT distinct format('"openshift_project": "%s"', namespace)
    FROM openshift_pod_usage_line_items_daily
    WHERE source = {{ocp_source_uuid}}
    AND month = {{month}}
    AND year = {{year}}
    AND interval_start >= {{start_date}}
    AND interval_start < date_add('day', 1, {{end_date}})
),
cte_agg_tags AS (
    SELECT array_agg(matched_tag) as matched_tags from cte_tag_matches
)
SELECT azure.accountname,
    azure.additionalinfo,
    azure.billingcurrency,
    azure.billingcurrencycode,
    azure.consumedservice,
    azure.costinbillingcurrency,
    azure.date,
    azure.effectiveprice,
    azure.frequency,
    azure.isazurecrediteligible,
    azure.metercategory,
    azure.metername,
    azure.metersubcategory,
    azure.productname,
    azure.publishername,
    azure.publishertype,
    azure.quantity,
    azure.resourcegroup,
    azure.resourceid,
    azure.resourcelocation,
    azure.resourcetype,
    azure.servicefamily,
    azure.serviceinfo1,
    azure.serviceinfo2,
    azure.servicename,
    azure.servicetier,
    azure.subscriptionguid,
    azure.subscriptionid,
    azure.subscriptionname,
    azure.tags,
    azure.term,
    azure.unitofmeasure,
    azure.unitprice,
    CASE WHEN resource_names.resourceid IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(tags, x ) != 0), ',') as matched_tag,
    azure.source as source,
    {{ocp_source_uuid}} as ocp_source,
    azure.year,
    azure.month,
    cast(day(azure.date) as varchar) as day
FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON azure.resourceid = resource_names.resourceid
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(tags, x) != 0)
    AND resource_names.resourceid IS NULL
WHERE azure.source = {{azure_source_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND azure.date >= {{start_date}}
    AND azure.date < date_add('day', 1, {{end_date}})
    AND (resource_names.resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL)
