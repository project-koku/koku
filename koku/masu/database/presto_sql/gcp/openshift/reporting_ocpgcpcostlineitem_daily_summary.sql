INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpgcpcostlineitem_project_daily_summary_p (
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
    account_id,
    project_id,
    project_name,
    instance_type,
    service_id,
    service_alias,
    sku_id,
    sku_alias,
    region,
    unit,
    usage_amount,
    currency,
    unblended_cost,
    markup_cost,
    project_markup_cost,
    pod_cost,
    tags,
    source_uuid,
    credit_amount,
    invoice_month
)
WITH cte_ocp_on_gcp_resource_id_joined AS(
    SELECT gcp.uuid as gcp_id,
        INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
        max(gcp.billing_account_id) as account_id,
        max(gcp.project_id) as project_id,
        max(gcp.project_name) as project_name,
        max(gcp.service_id) as service_id,
        max(gcp.service_description) as service_alias,
        max(gcp.sku_id) as sku_id,
        max(gcp.sku_description) as sku_alias,
        max(gcp.usage_start_time) as usage_start,
        max(gcp.usage_end_time) as usage_end,
        max(nullif(gcp.location_region, '')) as region,
        max(json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]')) as instance_type,
        max(gcp.usage_pricing_unit) as unit,
        cast(sum(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
        max(json_format(json_parse(labels))) as tags,
        max(gcp.currency) as currency,
        max(gcp.cost_type) as line_item_type,
        cast(sum(gcp.cost) AS decimal(24,9)) as unblended_cost,
        cast(sum(gcp.cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
        sum(((cast(COALESCE(json_extract_scalar(json_parse(credits), '$["amount"]'), '0')AS decimal(24,9)))*1000000)/1000000) as credit_amount,
        gcp.invoice_month as invoice_month,
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
    FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON gcp.usage_start_time = ocp.usage_start
    WHERE gcp.source = '{{gcp_source_uuid | sqlsafe}}'
        AND gcp.year = '{{year | sqlsafe}}'
        AND gcp.month = '{{month | sqlsafe}}'
        AND gcp.usage_start_time >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.cluster_id = '{{cluster_id | sqlsafe}}'
        AND ocp.report_period_id = {{report_period_id | sqlsafe}}
        AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
        AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
    GROUP BY gcp.uuid, ocp.namespace, ocp.data_source, gcp.invoice_month
),
cte_ocp_on_gcp_tag_joined AS (
    SELECT gcp.uuid as gcp_id,
        INTEGER '{{bill_id | sqlsafe}}' as cost_entry_bill_id,
        max(gcp.billing_account_id) as account_id,
        max(gcp.project_id) as project_id,
        max(gcp.project_name) as project_name,
        max(gcp.service_id) as service_id,
        max(gcp.service_description) as service_alias,
        max(gcp.sku_id) as sku_id,
        max(gcp.sku_description) as sku_alias,
        max(gcp.usage_start_time) as usage_start,
        max(gcp.usage_end_time) as usage_end,
        max(nullif(gcp.location_region, '')) as region,
        max(json_extract_scalar(json_parse(gcp.system_labels), '$["compute.googleapis.com/machine_spec"]')) as instance_type,
        max(gcp.usage_pricing_unit) as unit,
        cast(sum(gcp.usage_amount_in_pricing_units) AS decimal(24,9)) as usage_amount,
        max(gcp.labels) as tags,
        max(gcp.currency) as currency,
        max(gcp.cost_type) as line_item_type,
        cast(sum(gcp.cost) AS decimal(24,9)) as unblended_cost,
        cast(sum(gcp.cost * {{markup | sqlsafe}}) AS decimal(24,9)) as markup_cost,
        sum(((cast(COALESCE(json_extract_scalar(json_parse(credits), '$["amount"]'), '0')AS decimal(24,9)))*1000000)/1000000) as credit_amount,
        gcp.invoice_month as invoice_month,
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
    FROM hive.{{schema | sqlsafe}}.gcp_openshift_daily as gcp
    JOIN postgres.{{ schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON date(gcp.usage_start_time) = ocp.usage_start
            AND (
                json_extract_scalar(json_parse(gcp.labels), '$.openshift_project') = lower(ocp.namespace)
                    OR json_extract_scalar(json_parse(gcp.labels), '$.openshift_node') = lower(ocp.node)
                    OR json_extract_scalar(json_parse(gcp.labels), '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                    OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(json_format(ocp.pod_labels), replace(x, ' ')) != 0))
                    OR (gcp.matched_tag != '' AND any_match(split(gcp.matched_tag, ','), x->strpos(json_format(ocp.volume_labels), replace(x, ' ')) != 0))
                )
    WHERE gcp.source = '{{gcp_source_uuid | sqlsafe}}'
        AND gcp.year = '{{year | sqlsafe}}'
        AND gcp.month = '{{month | sqlsafe}}'
        AND gcp.usage_start_time >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.report_period_id = {{report_period_id | sqlsafe}}
        AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
        AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
    GROUP BY gcp.uuid, ocp.namespace, ocp.data_source, gcp.invoice_month
),
cte_ocp_on_gcp_joined AS (
    SELECT *
    FROM cte_ocp_on_gcp_resource_id_joined

    UNION

    SELECT tag.*
    FROM cte_ocp_on_gcp_tag_joined as tag
    LEFT JOIN cte_ocp_on_gcp_resource_id_joined as rid
        ON tag.gcp_id = rid.gcp_id
    WHERE rid.gcp_id IS NULL
),
cte_project_counts AS (
    SELECT gcp_id,
        count(DISTINCT namespace) as project_count
    FROM cte_ocp_on_gcp_joined
    GROUP BY gcp_id
),
cte_data_source_counts AS (
    SELECT gcp_id,
        namespace,
        count(DISTINCT data_source) as data_source_count
    FROM cte_ocp_on_gcp_joined
    GROUP BY gcp_id, namespace
)
SELECT uuid(),
    ocp_gcp.report_period_id,
    ocp_gcp.cluster_id,
    ocp_gcp.cluster_alias,
    ocp_gcp.data_source,
    ocp_gcp.namespace,
    ocp_gcp.node,
    ocp_gcp.persistentvolumeclaim,
    ocp_gcp.persistentvolume,
    ocp_gcp.storageclass,
    NULL as pod_labels,
    NULL as resource_id,
    date(ocp_gcp.usage_start) as usage_start,
    date(ocp_gcp.usage_end) as usage_end,
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
    ocp_gcp.account_id,
    ocp_gcp.project_id as project_id,
    ocp_gcp.project_name as project_name,
    ocp_gcp.instance_type,
    ocp_gcp.service_id,
    ocp_gcp.service_alias,
    ocp_gcp.sku_id as sku_id,
    ocp_gcp.sku_alias as sku_alias,
    ocp_gcp.region,
    ocp_gcp.unit,
    ocp_gcp.usage_amount / pc.project_count / dsc.data_source_count as usage_amount,
    ocp_gcp.currency as currency,
    ocp_gcp.unblended_cost / pc.project_count / dsc.data_source_count as unblended_cost,
    ocp_gcp.unblended_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9)) as markup_cost,
    ocp_gcp.unblended_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9)) as project_markup_cost,
    ocp_gcp.unblended_cost / pc.project_count / dsc.data_source_count as pod_cost,
    json_parse(ocp_gcp.tags) as tags,
    UUID '{{gcp_source_uuid | sqlsafe}}' as source_uuid,
    ocp_gcp.credit_amount as credit_amount,
    ocp_gcp.invoice_month as invoice_month
FROM cte_ocp_on_gcp_joined as ocp_gcp
JOIN cte_project_counts AS pc
    ON ocp_gcp.gcp_id = pc.gcp_id
JOIN cte_data_source_counts AS dsc
    ON ocp_gcp.gcp_id = dsc.gcp_id
        AND ocp_gcp.namespace = dsc.namespace
;
