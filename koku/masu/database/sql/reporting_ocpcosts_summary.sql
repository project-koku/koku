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
        0::decimal as infra_cost,
        0::decimal as project_infra_cost
    FROM reporting_ocpusagelineitem_daily_summary as usageli
    WHERE date(usageli.usage_start) >= '{start_date}'
        AND date(usageli.usage_start) <= '{end_date}'
        AND usageli.cluster_id = '{cluster_id}'

    UNION ALL

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
        0::decimal as infra_cost,
        0::decimal as project_infra_cost
    FROM reporting_ocpstoragelineitem_daily_summary as storageli
    WHERE date(storageli.usage_start) >= '{start_date}'
        AND date(storageli.usage_start) <= '{end_date}'
        AND storageli.cluster_id = '{cluster_id}'

    UNION ALL

    SELECT ocp_aws.usage_start,
        ocp_aws.usage_end,
        ocp_aws.cluster_id,
        ocp_aws.cluster_alias,
        ocp_aws.namespace,
        ocp_aws.pod,
        ocp_aws.node,
        ocp_aws.pod_labels,
        0::decimal AS pod_charge_cpu_core_hours,
        0::decimal AS pod_charge_memory_gigabyte_hours,
        0::decimal AS persistentvolumeclaim_charge_gb_month,
        ocp_aws.unblended_cost AS infra_cost,
        ocp_aws.pod_cost AS project_infra_cost
    FROM reporting_ocpawscostlineitem_project_daily_summary AS ocp_aws
    WHERE date(ocp_aws.usage_start) >= '{start_date}'
        AND date(ocp_aws.usage_start) <= '{end_date}'
        AND ocp_aws.cluster_id = '{cluster_id}'
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpcosts_summary
WHERE date(usage_start) >= '{start_date}'
    AND date(usage_start) <= '{end_date}'
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
