CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.usage_start,
        li.usage_end,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        -- persistentvolumeclaim_labels values will win in
        -- the volume label merge
        li.persistentvolume_labels || li.persistentvolumeclaim_labels as volume_labels,
        max(li.persistentvolumeclaim_capacity_bytes) * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte,
        sum(li.persistentvolumeclaim_capacity_byte_seconds) /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte_months,
        sum(li.volume_request_storage_byte_seconds) /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as volume_request_storage_gigabyte_months,
        sum(li.persistentvolumeclaim_usage_byte_seconds) /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as persistentvolumeclaim_usage_gigabyte_months
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li
    WHERE usage_start >= {{start_date}}
        AND usage_start <= {{end_date}}
        AND cluster_id = {{cluster_id}}
    GROUP BY li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.usage_start,
        li.usage_end,
        li.namespace,
        li.node,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels,
        li.persistentvolume,
        li.persistentvolumeclaim,
        li.storageclass
)
;

-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
    AND data_source = 'Storage'
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
    report_period_id,
    cluster_id,
    cluster_alias,
    data_source,
    namespace,
    node,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    usage_start,
    usage_end,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months
)
    SELECT report_period_id,
        cluster_id,
        cluster_alias,
        'Storage',
        namespace,
        node,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        usage_start,
        usage_end,
        volume_labels,
        persistentvolumeclaim_capacity_gigabyte,
        persistentvolumeclaim_capacity_gigabyte_months,
        volume_request_storage_gigabyte_months,
        persistentvolumeclaim_usage_gigabyte_months
    FROM reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}}
;
