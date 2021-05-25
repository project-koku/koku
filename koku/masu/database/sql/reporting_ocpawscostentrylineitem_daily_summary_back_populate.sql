-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary
WHERE usage_start >= {{start_date}}::date
    AND usage_start <= {{end_date}}::date
    AND report_period_id = {{report_period_id | sqlsafe}}
;


-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpawscostlineitem_daily_summary (
    uuid,
    report_period_id,
    cluster_id,
    cluster_alias,
    namespace,
    node,
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
    tags,
    usage_amount,
    currency_code,
    unblended_cost,
    markup_cost,
    shared_projects,
    source_uuid
)
    SELECT uuid_generate_v4(),
        report_period_id,
        cluster_id,
        cluster_alias,
        array_agg(DISTINCT namespace) as namespace,
        node,
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
        tags,
        sum(usage_amount) as usage_amount,
        max(currency_code) as currency_code,
        sum(unblended_cost) as unblended_cost,
        sum(markup_cost) as markup_cost,
        count(DISTINCT namespace) as shared_projects,
        source_uuid
    FROM reporting_ocpawscostlineitem_project_daily_summary
    WHERE report_period_id = {{report_period_id | sqlsafe}}
        AND usage_start >= date({{start_date}})
        AND usage_start <= date({{end_date}})
    GROUP BY report_period_id,
        cluster_id,
        cluster_alias,
        node,
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
        tags,
        source_uuid
;

INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    uuid,
    report_period_id,
    usage_start,
    usage_end,
    cluster_id,
    cluster_alias,
    namespace,
    data_source,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    resource_id,
    pod_labels,
    volume_labels,
    source_uuid,
    infrastructure_raw_cost,
    infrastructure_project_raw_cost,
    infrastructure_usage_cost,
    supplementary_usage_cost,
    pod_usage_cpu_core_hours,
    pod_request_cpu_core_hours,
    pod_limit_cpu_core_hours,
    pod_usage_memory_gigabyte_hours,
    pod_request_memory_gigabyte_hours,
    pod_limit_memory_gigabyte_hours,
    node_capacity_cpu_cores,
    node_capacity_cpu_core_hours,
    node_capacity_memory_gigabytes,
    node_capacity_memory_gigabyte_hours,
    cluster_capacity_cpu_core_hours,
    cluster_capacity_memory_gigabyte_hours,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months
)
    SELECT uuid_generate_v4() as uuid,
        ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        max(ocp_aws.persistentvolume),
        max(ocp_aws.storageclass),
        ocp_aws.resource_id,
        CASE WHEN ocp_aws.data_source = 'Pod'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as pod_labels,
        CASE WHEN ocp_aws.data_source = 'Storage'
            THEN ocp_aws.pod_labels
            ELSE '{}'::jsonb
        END as volume_labels,
        rp.provider_id as source_uuid,
        sum(ocp_aws.unblended_cost + ocp_aws.markup_cost) AS infrastructure_raw_cost,
        sum(ocp_aws.pod_cost + ocp_aws.project_markup_cost) AS infrastructure_project_raw_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as infrastructure_usage_cost,
        '{"cpu": 0.000000000, "memory": 0.000000000, "storage": 0.000000000}'::jsonb as supplementary_usage_cost,
        0 as pod_usage_cpu_core_hours,
        0 as pod_request_cpu_core_hours,
        0 as pod_limit_cpu_core_hours,
        0 as pod_usage_memory_gigabyte_hours,
        0 as pod_request_memory_gigabyte_hours,
        0 as pod_limit_memory_gigabyte_hours,
        0 as node_capacity_cpu_cores,
        0 as node_capacity_cpu_core_hours,
        0 as node_capacity_memory_gigabytes,
        0 as node_capacity_memory_gigabyte_hours,
        0 as cluster_capacity_cpu_core_hours,
        0 as cluster_capacity_memory_gigabyte_hours,
        0 as persistentvolumeclaim_capacity_gigabyte,
        0 as persistentvolumeclaim_capacity_gigabyte_months,
        0 as volume_request_storage_gigabyte_months,
        0 as persistentvolumeclaim_usage_gigabyte_months
    FROM {{schema | sqlsafe}}.reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON ocp_aws.cluster_id = rp.cluster_id
            AND DATE_TRUNC('month', ocp_aws.usage_start)::date  = date(rp.report_period_start)
    WHERE ocp_aws.usage_start >= {{start_date}}::date
        AND ocp_aws.usage_start <= {{end_date}}::date
        AND ocp_aws.report_period_id = {{report_period_id | sqlsafe}}
    GROUP BY ocp_aws.report_period_id,
        ocp_aws.usage_start,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.data_source,
        ocp_aws.node,
        ocp_aws.persistentvolumeclaim,
        ocp_aws.resource_id,
        ocp_aws.pod_labels,
        rp.provider_id
;
