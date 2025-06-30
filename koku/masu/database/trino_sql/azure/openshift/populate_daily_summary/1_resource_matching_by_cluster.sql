DELETE FROM hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp
WHERE source = {{cloud_provider_uuid}}
AND ocp_source = {{ocp_provider_uuid}}
AND year = {{year}}
AND month = {{month}};

INSERT INTO hive.{{schema | sqlsafe}}.managed_azure_openshift_daily_temp (
    row_uuid,
    usage_start,
    resource_id,
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
    date,
    metername,
    complete_resource_id,
    tags,
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
    WHERE source = {{cloud_provider_uuid}}
        AND year = {{year}}
        AND month = {{month}}
        AND date >= {{start_date}}
        AND date < date_add('day', 1, {{end_date}})
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
    SELECT resource_names.resourceid
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_nodes AS nodes
        ON nodes.node != ''
        AND strpos(resource_names.resourceid, nodes.node) != 0

    UNION

    SELECT resource_names.resourceid
    FROM cte_azure_resource_names AS resource_names
    JOIN cte_array_agg_volumes AS volumes
        ON (
            (volumes.persistentvolume != '' and strpos(resource_names.resourceid, volumes.persistentvolume) != 0)
            OR (volumes.csi_volume_handle != '' and strpos(resource_names.resourceid, volumes.csi_volume_handle) != 0)
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
        AND provider_type = 'Azure'
)
SELECT
    azure.row_uuid,
    azure.date as usage_start,
    split_part(azure.resourceid, '/', 9) as resource_id,
    coalesce(nullif(azure.servicename, ''), azure.metercategory) as service_name,
    CASE
        WHEN coalesce(nullif(servicename, ''), metercategory) = 'Virtual Network'
            AND lower(consumedservice)='microsoft.compute'
            AND json_exists(lower(additionalinfo), 'strict $.datatransferdirection')
            AND resource_names.resourceid IS NOT NULL
                THEN json_extract_scalar(lower(azure.additionalinfo), '$.datatransferdirection')
        ELSE NULL
    END as data_transfer_direction,
    json_extract_scalar(json_parse(azure.additionalinfo), '$.ServiceType') as instance_type,
    coalesce(nullif(azure.subscriptionid, ''), azure.subscriptionguid) as subscription_guid,
    azure.subscriptionname as subscription_name,
    azure.resourcelocation as resource_location,
    CASE
        WHEN split_part(azure.unitofmeasure, ' ', 2) = 'Hours'
            THEN  'Hrs'
        WHEN split_part(azure.unitofmeasure, ' ', 2) = 'GB/Month'
            THEN  'GB-Mo'
        WHEN split_part(azure.unitofmeasure, ' ', 2) != ''
            THEN  split_part(azure.unitofmeasure, ' ', 2)
        ELSE azure.unitofmeasure
    END as unit_of_measure,
    (azure.quantity * (CASE
        WHEN regexp_like(split_part(azure.unitofmeasure, ' ', 1), '^\d+(\.\d+)?$') AND NOT (azure.unitofmeasure = '100 Hours' AND azure.metercategory='Virtual Machines') AND NOT split_part(azure.unitofmeasure, ' ', 2) = ''
            THEN cast(split_part(azure.unitofmeasure, ' ', 1) as INTEGER)
            ELSE 1
        END)
    ) as usage_quantity,
    coalesce(nullif(azure.billingcurrencycode, ''), azure.billingcurrency) as currency,
    azure.costinbillingcurrency as pretax_cost,
    azure.date,
    azure.metername,
    azure.resourceid as complete_resource_id,
    json_format(
        cast(
            map_filter(
                cast(json_parse(azure.tags) as map(varchar, varchar)),
                (k, v) -> contains(etk.enabled_keys, k)
            ) as json
        )
    ) as tags, -- Limit tag keys to enabled keys
    CASE WHEN resource_names.resourceid IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END as resource_id_matched,
    array_join(filter(tag_matches.matched_tags, x -> STRPOS(tags, x ) != 0), ',') as matched_tag,
    azure.source as source,
    {{ocp_provider_uuid}} as ocp_source,
    azure.year,
    azure.month,
    cast(day(azure.date) as varchar) as day
FROM hive.{{schema | sqlsafe}}.azure_line_items AS azure
CROSS JOIN cte_enabled_tag_keys as etk
LEFT JOIN cte_matchable_resource_names AS resource_names
    ON azure.resourceid = resource_names.resourceid
LEFT JOIN cte_agg_tags AS tag_matches
    ON any_match(tag_matches.matched_tags, x->strpos(tags, x) != 0)
    AND resource_names.resourceid IS NULL
WHERE azure.source = {{cloud_provider_uuid}}
    AND azure.year = {{year}}
    AND azure.month= {{month}}
    AND azure.date >= {{start_date}}
    AND azure.date < date_add('day', 1, {{end_date}})
    AND (resource_names.resourceid IS NOT NULL OR tag_matches.matched_tags IS NOT NULL);
