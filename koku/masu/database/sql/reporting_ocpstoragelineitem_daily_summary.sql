CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{uuid} AS (
    SELECT  li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.node,
        li.usage_start,
        li.usage_end,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        -- persistentvolumeclaim_labels values will win in
        -- the volume label merge
        persistentvolume_labels || persistentvolumeclaim_labels as volume_labels,
        li.persistentvolumeclaim_capacity_bytes * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte,
        li.persistentvolumeclaim_capacity_byte_seconds /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte_months,
        li.volume_request_storage_byte_seconds /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as volume_request_storage_gigabyte_months,
        li.persistentvolumeclaim_usage_byte_seconds /
            86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day')
            * POWER(2, -30) as persistentvolumeclaim_usage_gigabyte_months
    FROM {schema}.reporting_ocpstoragelineitem_daily AS li
    WHERE usage_start >= '{start_date}'
        AND usage_start <= '{end_date}'
        AND cluster_id = '{cluster_id}'
)
;

-- Clear out old entries first
DELETE FROM {schema}.reporting_ocpstoragelineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
    AND cluster_id = '{cluster_id}'
;

-- Populate the daily aggregate line item data
INSERT INTO {schema}.reporting_ocpstoragelineitem_daily_summary (
    cluster_id,
    cluster_alias,
    namespace,
    pod,
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
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
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
    FROM reporting_ocpstoragelineitem_daily_summary_{uuid}
;
