INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpazurecostlineitem_project_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    pod_labels,
    resource_id,
    usage_start,
    usage_end,
    cost_entry_bill_id,
    subscription_guid,
    instance_type,
    service_name,
    resource_location,
    usage_quantity,
    pretax_cost,
    markup_cost,
    currency,
    unit_of_measure,
    pod_cost,
    project_markup_cost,
    tags,
    source_uuid
)
WITH cte_ocp_on_azure_joined AS (
    SELECT azure.uuid as azure_id,
        max(split_part(coalesce(resourceid, instanceid), '/', 9)) as resource_id,
        max(coalesce(date, usagedatetime)) as usage_start,
        max(coalesce(date, usagedatetime)) as usage_end,
        max(json_extract_scalar(json_parse(azure.additionalinfo), '$.ServiceType')) as instance_type,
        max(coalesce(subscriptionid, subscriptionguid)) as subscription_guid,
        max(azure.resourcelocation) as resource_location,

        max(CASE
            WHEN split_part(unitofmeasure, ' ', 2) != '' AND NOT (unitofmeasure = '100 Hours' AND metercategory='Virtual Machines')
                THEN cast(split_part(unitofmeasure, ' ', 1) as integer)
            ELSE 1
            END) as multiplier,
        max(CASE
            WHEN split_part(unitofmeasure, ' ', 2) = 'Hours'
                THEN  'Hrs'
            WHEN split_part(unitofmeasure, ' ', 2) = 'GB/Month'
                THEN  'GB-Mo'
            WHEN split_part(unitofmeasure, ' ', 2) != ''
                THEN  split_part(unitofmeasure, ' ', 2)
            ELSE unitofmeasure
        END) as unit_of_measure,

        max(cast(coalesce(azure.quantity, azure.usagequantity) as decimal(24,9))) as usage_quantity,
        max(cast(coalesce(azure.costinbillingcurrency, azure.pretaxcost) as decimal(24,9))) as pretax_cost,
        max(coalesce(billingcurrencycode, currency)) as currency,
        max(azure.resource_id_matched) as resource_id_matched,
        max(azure.tags) as tags,
        max(azure.servicename) as service_name,
        max(ocp.report_period_id) as report_period_id,
        max(ocp.cluster_id) as cluster_id,
        max(ocp.cluster_alias) as cluster_alias,
        ocp.namespace,
        ocp.data_source,
        max(ocp.node) as node,
        max(json_format(ocp.pod_labels)) as pod_labels,
        sum(ocp.pod_usage_cpu_core_hours) as pod_usage_cpu_core_hours,
        sum(ocp.pod_request_cpu_core_hours) as pod_request_cpu_core_hours,
        sum(ocp.pod_limit_cpu_core_hours) as pod_limit_cpu_core_hours,
        sum(ocp.pod_usage_memory_gigabyte_hours) as pod_usage_memory_gigabyte_hours,
        sum(ocp.pod_request_memory_gigabyte_hours) as pod_request_memory_gigabyte_hours,
        max(ocp.node_capacity_cpu_cores) as node_capacity_cpu_cores,
        max(ocp.node_capacity_cpu_core_hours) as node_capacity_cpu_core_hours,
        max(ocp.node_capacity_memory_gigabytes) as node_capacity_memory_gigabytes,
        max(ocp.node_capacity_memory_gigabyte_hours) as node_capacity_memory_gigabyte_hours,
        max(ocp.cluster_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
        max(ocp.cluster_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours,
        max(ocp.persistentvolumeclaim) as persistentvolumeclaim,
        max(ocp.persistentvolume) as persistentvolume,
        max(ocp.storageclass) as storageclass,
        max(json_format(volume_labels)) as volume_labels,
        max(ocp.persistentvolumeclaim_capacity_gigabyte) as persistentvolumeclaim_capacity_gigabyte,
        max(ocp.persistentvolumeclaim_capacity_gigabyte_months) as persistentvolumeclaim_capacity_gigabyte_months,
        sum(ocp.volume_request_storage_gigabyte_months) as volume_request_storage_gigabyte_months,
        sum(ocp.persistentvolumeclaim_usage_gigabyte_months) as persistentvolumeclaim_usage_gigabyte_months
    FROM hive.{{schema | sqlsafe}}.azure_openshift_daily as azure
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON coalesce(azure.date, azure.usagedatetime) = ocp.usage_start
            AND (
                split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) = ocp.node
                    OR split_part(coalesce(azure.resourceid, azure.instanceid), '/', 9) = ocp.persistentvolume
                    OR json_extract_scalar(azure.tags, '$.openshift_project') = lower(ocp.namespace)
                    OR json_extract_scalar(azure.tags, '$.openshift_node') = lower(ocp.node)
                    OR json_extract_scalar(azure.tags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                    OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(json_format(ocp.pod_labels), replace(x, ' ')) != 0))
                    OR (azure.matched_tag != '' AND any_match(split(azure.matched_tag, ','), x->strpos(json_format(ocp.volume_labels), replace(x, ' ')) != 0))
            )
    WHERE azure.source = '{{azure_source_uuid | sqlsafe}}'
        AND azure.year = '{{year | sqlsafe}}'
        AND azure.month = '{{month | sqlsafe}}'
        AND coalesce(azure.date, azure.usagedatetime) >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND coalesce(azure.date, azure.usagedatetime) < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.report_period_id = {{report_period_id | sqlsafe}}
        AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
        AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
    GROUP BY azure.uuid, ocp.namespace, ocp.data_source
),
cte_project_counts AS (
    SELECT azure_id,
        count(DISTINCT namespace) as project_count
    FROM cte_ocp_on_azure_joined
    GROUP BY azure_id
),
cte_data_source_counts AS (
    SELECT azure_id,
        namespace,
        count(DISTINCT data_source) as data_source_count
    FROM cte_ocp_on_azure_joined
    GROUP BY azure_id, namespace
)
SELECT uuid(),
    ocp_azure.report_period_id,
    ocp_azure.cluster_id,
    ocp_azure.cluster_alias,
    ocp_azure.data_source,
    ocp_azure.namespace,
    ocp_azure.node,
    ocp_azure.persistentvolumeclaim,
    ocp_azure.persistentvolume,
    ocp_azure.storageclass,
    CASE WHEN ocp_azure.pod_labels IS NOT NULL
        THEN cast(
            map_concat(
                cast(json_parse(ocp_azure.pod_labels) as map(varchar, varchar)),
                cast(json_parse(ocp_azure.tags) as map(varchar, varchar))
            ) as JSON)
        ELSE cast(
            map_concat(
                cast(json_parse(ocp_azure.volume_labels) as map(varchar, varchar)),
                cast(json_parse(ocp_azure.tags) as map(varchar, varchar))
            ) as JSON)
    END as pod_labels,
    ocp_azure.resource_id,
    date(ocp_azure.usage_start) as usage_start,
    date(ocp_azure.usage_end) as usage_end,
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
    ocp_azure.subscription_guid,
    ocp_azure.instance_type,
    ocp_azure.service_name,
    ocp_azure.resource_location,
    ocp_azure.usage_quantity / pc.project_count / dsc.data_source_count as usage_quantity,
    ocp_azure.pretax_cost / pc.project_count / dsc.data_source_count as pretax_cost,
    ocp_azure.pretax_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9)) as markup_cost,
    ocp_azure.currency,
    ocp_azure.unit_of_measure,
    CASE WHEN ocp_azure.resource_id_matched = TRUE AND ocp_azure.data_source = 'Pod'
        THEN (ocp_azure.{{node_column | sqlsafe}} / ocp_azure.{{cluster_column | sqlsafe}}) * ocp_azure.pretax_cost / dsc.data_source_count
        ELSE ocp_azure.pretax_cost / pc.project_count / dsc.data_source_count
    END as pod_cost,
    CASE WHEN ocp_azure.resource_id_matched = TRUE AND ocp_azure.data_source = 'Pod'
        THEN (ocp_azure.{{node_column | sqlsafe}} / ocp_azure.{{cluster_column | sqlsafe}}) * ocp_azure.pretax_cost * cast({{markup}} as decimal(24,9)) / dsc.data_source_count
        ELSE ocp_azure.pretax_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9))
    END as project_markup_cost,
    json_parse(ocp_azure.tags) as tags,
    UUID '{{azure_source_uuid | sqlsafe}}' as source_uuid
FROM cte_ocp_on_azure_joined AS ocp_azure
JOIN cte_project_counts AS pc
    ON ocp_azure.azure_id = pc.azure_id
JOIN cte_data_source_counts AS dsc
    ON ocp_azure.azure_id = dsc.azure_id
        AND ocp_azure.namespace = dsc.namespace
;
