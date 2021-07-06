INSERT INTO postgres.{{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary (
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
    resource_id,
    usage_start,
    usage_end,
    product_code,
    product_family,
    instance_type,
    cost_entry_bill_id,
    usage_account_id,
    account_alias_id,
    availability_zone,
    region,
    unit,
    usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    pod_cost,
    project_markup_cost,
    pod_labels,
    tags,
    source_uuid
)
WITH cte_ocp_on_aws_joined AS (
    SELECT aws.uuid as aws_id,
        max(aws.lineitem_resourceid) as resource_id,
        max(aws.lineitem_usagestartdate) as usage_start,
        max(aws.lineitem_usagestartdate) as usage_end,
        max(aws.lineitem_productcode) as product_code,
        max(aws.product_productfamily) as product_family,
        max(aws.product_instancetype) as instance_type,
        max(aws.lineitem_usageaccountid) as usage_account_id,
        max(aws.lineitem_availabilityzone) as availability_zone,
        max(aws.product_region) as region,
        max(aws.pricing_unit) as unit,
        max(aws.lineitem_usageamount) as usage_amount,
        max(aws.lineitem_currencycode) as currency_code,
        max(aws.lineitem_unblendedcost) as unblended_cost,
        max(aws.resourcetags) as tags,
        max(aws.resource_id_matched) as resource_id_matched,
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
    FROM hive.{{schema | sqlsafe}}.aws_openshift_daily as aws
    JOIN postgres.{{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary as ocp
        ON aws.lineitem_usagestartdate = ocp.usage_start
            AND (
                aws.lineitem_resourceid = ocp.resource_id
                    OR json_extract_scalar(aws.resourcetags, '$.openshift_project') = lower(ocp.namespace)
                    OR json_extract_scalar(aws.resourcetags, '$.openshift_node') = lower(ocp.node)
                    OR json_extract_scalar(aws.resourcetags, '$.openshift_cluster') IN (lower(ocp.cluster_id), lower(ocp.cluster_alias))
                    OR any_match(split(aws.matched_tag, ','), x->strpos(json_format(ocp.pod_labels), replace(x, ' ')) != 0)
                    OR any_match(split(aws.matched_tag, ','), x->strpos(json_format(ocp.volume_labels), replace(x, ' ')) != 0)
            )
    WHERE aws.source = '{{aws_source_uuid | sqlsafe}}'
        AND aws.year = '{{year | sqlsafe}}'
        AND aws.month = '{{month | sqlsafe}}'
        AND aws.lineitem_usagestartdate >= TIMESTAMP '{{start_date | sqlsafe}}'
        AND aws.lineitem_usagestartdate < date_add('day', 1, TIMESTAMP '{{end_date | sqlsafe}}')
        AND ocp.report_period_id = {{report_period_id | sqlsafe}}
        AND ocp.usage_start >= date('{{start_date | sqlsafe}}')
        AND ocp.usage_start <= date('{{end_date | sqlsafe}}')
    GROUP BY aws.uuid, ocp.namespace, ocp.data_source
),
cte_project_counts AS (
    SELECT aws_id,
        count(DISTINCT namespace) as project_count
    FROM cte_ocp_on_aws_joined
    GROUP BY aws_id
),
cte_data_source_counts AS (
    SELECT aws_id,
        namespace,
        count(DISTINCT data_source) as data_source_count
    FROM cte_ocp_on_aws_joined
    GROUP BY aws_id, namespace
)
SELECT uuid(),
    ocp_aws.report_period_id,
    ocp_aws.cluster_id,
    ocp_aws.cluster_alias,
    ocp_aws.data_source,
    ocp_aws.namespace,
    ocp_aws.node,
    ocp_aws.persistentvolumeclaim,
    ocp_aws.persistentvolume,
    ocp_aws.storageclass,
    ocp_aws.resource_id,
    date(ocp_aws.usage_start) as usage_start,
    date(ocp_aws.usage_end) as usage_end,
    ocp_aws.product_code,
    ocp_aws.product_family,
    ocp_aws.instance_type,
    {{bill_id | sqlsafe}} as cost_entry_bill_id,
    ocp_aws.usage_account_id,
    aa.id as account_alias_id,
    ocp_aws.availability_zone,
    ocp_aws.region,
    ocp_aws.unit,
    ocp_aws.usage_amount / pc.project_count / dsc.data_source_count as usage_amount,
    ocp_aws.currency_code,
    ocp_aws.unblended_cost / pc.project_count / dsc.data_source_count as unblended_cost,
    ocp_aws.unblended_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9)) as markup_cost,
    CASE WHEN ocp_aws.resource_id_matched = TRUE AND ocp_aws.data_source = 'Pod'
        THEN (ocp_aws.pod_usage_cpu_core_hours / ocp_aws.cluster_capacity_cpu_core_hours) * ocp_aws.unblended_cost
        ELSE ocp_aws.unblended_cost / pc.project_count / dsc.data_source_count
    END as pod_cost,
    CASE WHEN ocp_aws.resource_id_matched = TRUE AND ocp_aws.data_source = 'Pod'
        THEN (ocp_aws.pod_usage_cpu_core_hours / ocp_aws.cluster_capacity_cpu_core_hours) * ocp_aws.unblended_cost * cast({{markup}} as decimal(24,9))
        ELSE ocp_aws.unblended_cost / pc.project_count / dsc.data_source_count * cast({{markup}} as decimal(24,9))
    END as project_markup_cost,
    CASE WHEN ocp_aws.pod_labels IS NOT NULL
        THEN cast(
            map_concat(
                cast(json_parse(ocp_aws.pod_labels) as map(varchar, varchar)),
                cast(json_parse(ocp_aws.tags) as map(varchar, varchar))
            ) as JSON)
        ELSE cast(
            map_concat(
                cast(json_parse(ocp_aws.volume_labels) as map(varchar, varchar)),
                cast(json_parse(ocp_aws.tags) as map(varchar, varchar))
            ) as JSON)
    END as pod_labels,
    json_parse(ocp_aws.tags) as tags,
    UUID '{{aws_source_uuid | sqlsafe}}' as source_uuid
FROM cte_ocp_on_aws_joined AS ocp_aws
JOIN cte_project_counts AS pc
    ON ocp_aws.aws_id = pc.aws_id
JOIN cte_data_source_counts AS dsc
    ON ocp_aws.aws_id = dsc.aws_id
        AND ocp_aws.namespace = dsc.namespace
LEFT JOIN postgres.{{schema | sqlsafe}}.reporting_awsaccountalias AS aa
    ON ocp_aws.usage_account_id = aa.account_id
;
