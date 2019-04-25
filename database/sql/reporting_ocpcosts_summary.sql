CREATE TEMPORARY TABLE reporting_ocpcosts_summary_{uuid} AS (
    SELECT usageli.usage_start,
        usageli.usage_end,
        usageli.cluster_id,
        usageli.cluster_alias,
        usageli.namespace,
        usageli.pod,
        usageli.node,
        usageli.pod_labels,
        COALESCE(usageli.pod_charge_cpu_core_hours, 0.0::decimal) AS pod_charge_cpu_core_hours,
        COALESCE(usageli.pod_charge_memory_gigabyte_hours, 0.0::decimal) AS pod_charge_memory_gigabyte_hours,
        0::decimal AS persistentvolumeclaim_charge_gb_month,
        COALESCE(ocp_aws.infra_cost, 0) as infra_cost,
        COALESCE(ocp_aws.project_infra_cost, 0) as project_infra_cost
    FROM reporting_ocpusagelineitem_daily_summary as usageli
    LEFT JOIN (
        SELECT cluster_id,
            usage_start,
            namespace,
            node,
            sum(ocp_aws.unblended_cost / ocp_aws.shared_projects) as infra_cost,
            sum(ocp_aws.project_cost) as project_infra_cost
        FROM reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
        GROUP BY cluster_id,
                usage_start,
                namespace,
                node
    ) as ocp_aws
        ON usageli.usage_start = ocp_aws.usage_start
            AND usageli.cluster_id = ocp_aws.cluster_id
            AND usageli.namespace = ocp_aws.namespace
            AND usageli.node = ocp_aws.node
    WHERE usageli.usage_start >= '{start_date}'
        AND usageli.usage_start <= '{end_date}'
        AND usageli.cluster_id = '{cluster_id}'

    UNION

    SELECT storageli.usage_start,
        storageli.usage_end,
        storageli.cluster_id,
        storageli.cluster_alias,
        storageli.namespace,
        storageli.pod,
        storageli.node,
        storageli.volume_labels as pod_labels,
        0::decimal AS pod_charge_cpu_core_hours,
        0::decimal AS pod_charge_memory_gigabyte_hours,
        COALESCE(storageli.persistentvolumeclaim_charge_gb_month, 0::decimal) AS persistentvolumeclaim_charge_gb_month,
        COALESCE(ocp_aws.infra_cost, 0::decimal) as infra_cost,
        COALESCE(ocp_aws.project_infra_cost, 0::decimal) as project_infra_cost
    FROM reporting_ocpstoragelineitem_daily_summary as storageli
    LEFT JOIN (
        SELECT cluster_id,
            usage_start,
            namespace,
            node,
            sum(ocp_aws.unblended_cost / ocp_aws.shared_projects) as infra_cost,
            sum(ocp_aws.project_cost) as project_infra_cost
        FROM reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
        GROUP BY cluster_id,
                usage_start,
                namespace,
                node
    ) as ocp_aws
        ON storageli.usage_start = ocp_aws.usage_start
            AND storageli.cluster_id = ocp_aws.cluster_id
            AND storageli.namespace = ocp_aws.namespace
            AND storageli.node = ocp_aws.node
    WHERE storageli.usage_start >= '{start_date}'
        AND storageli.usage_start <= '{end_date}'
        AND storageli.cluster_id = '{cluster_id}'
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpcosts_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cluster_id = '{cluster_id}'
;

-- Populate the ocp costs summary table
INSERT INTO reporting_ocpcosts_summary (
    cluster_id,
    cluster_alias,
    namespace,
    pod,
    node,
    usage_start,
    usage_end,
    pod_charge_cpu_core_hours,
    pod_charge_memory_gigabyte_hours,
    persistentvolumeclaim_charge_gb_month,
    infra_cost,
    project_infra_cost,
    pod_labels
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
        node,
        usage_start,
        usage_end,
        pod_charge_cpu_core_hours,
        pod_charge_memory_gigabyte_hours,
        persistentvolumeclaim_charge_gb_month,
        infra_cost,
        project_infra_cost,
        pod_labels
    FROM reporting_ocpcosts_summary_{uuid}
;
