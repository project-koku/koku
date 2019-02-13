CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{uuid} AS (
    SELECT  li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.pod,
        li.usage_start,
        li.usage_end,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        '{{}}'::jsonb as persistentvolume_labels,
        '{{}}'::jsonb as persistentvolumeclaim_labels,
        sum(li.persistentvolumeclaim_capacity_bytes * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
        sum(li.persistentvolumeclaim_capacity_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte_hours,
        sum(li.volume_request_storage_byte_seconds / 3600 * POWER(2, -30)) as volume_request_storage_gigabyte_hours,
        sum(li.persistentvolumeclaim_usage_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_usage_gigabyte_hours
    FROM reporting_ocpstoragelineitem_daily AS li
    WHERE usage_start >= '{start_date}'
        AND usage_start <= '{end_date}'
    GROUP BY li.cluster_id,
        li.cluster_alias,
        li.usage_start,
        li.usage_end,
        li.namespace,
        li.pod,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass

    UNION

        SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
        usage_start,
        usage_end,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        cast(concat('{{"', key, '": "', value, '"}}') as jsonb) as persistentvolume_labels,
        '{{}}'::jsonb as persistentvolumeclaim_labels,
        persistentvolumeclaim_capacity_gigabyte,
        persistentvolumeclaim_capacity_gigabyte_hours,
        volume_request_storage_gigabyte_hours,
        persistentvolumeclaim_usage_gigabyte_hours
    FROM (
        SELECT  li.cluster_id,
            li.cluster_alias,
            li.namespace,
            li.pod,
            li.usage_start,
            li.usage_end,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            li.key,
            li.value,
            '{{}}'::jsonb as persistentvolumeclaim_labels,
            sum(li.persistentvolumeclaim_capacity_bytes * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
            sum(li.persistentvolumeclaim_capacity_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte_hours,
            sum(li.volume_request_storage_byte_seconds / 3600 * POWER(2, -30)) as volume_request_storage_gigabyte_hours,
            sum(li.persistentvolumeclaim_usage_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_usage_gigabyte_hours
        FROM (
            SELECT cluster_id,
                cluster_alias,
                namespace,
                pod,
                usage_start,
                usage_end,
                persistentvolumeclaim,
                persistentvolume,
                storageclass,
                key,
                value,
                persistentvolumeclaim_capacity_bytes,
                persistentvolumeclaim_capacity_byte_seconds,
                volume_request_storage_byte_seconds,
                persistentvolumeclaim_usage_byte_seconds
            FROM reporting_ocpstoragelineitem_daily AS li,
                jsonb_each_text(li.persistentvolume_labels) persistentvolume_labels
        ) li
        WHERE usage_start >= '{start_date}'
            AND usage_start <= '{end_date}'
        GROUP BY li.cluster_id,
            li.cluster_alias,
            li.usage_start,
            li.usage_end,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            li.key,
            li.value
    ) t

    UNION

    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
        usage_start,
        usage_end,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        '{{}}'::jsonb  as persistentvolume_labels,
        cast(concat('{{"', key, '": "', value, '"}}') as jsonb)as persistentvolumeclaim_labels,
        persistentvolumeclaim_capacity_gigabyte,
        persistentvolumeclaim_capacity_gigabyte_hours,
        volume_request_storage_gigabyte_hours,
        persistentvolumeclaim_usage_gigabyte_hours
    FROM (
        SELECT  li.cluster_id,
            li.cluster_alias,
            li.namespace,
            li.pod,
            li.usage_start,
            li.usage_end,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            li.key,
            li.value,
            '{{}}'::jsonb as persistentvolume_labels,
            sum(li.persistentvolumeclaim_capacity_bytes * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte,
            sum(li.persistentvolumeclaim_capacity_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_capacity_gigabyte_hours,
            sum(li.volume_request_storage_byte_seconds / 3600 * POWER(2, -30)) as volume_request_storage_gigabyte_hours,
            sum(li.persistentvolumeclaim_usage_byte_seconds / 3600 * POWER(2, -30)) as persistentvolumeclaim_usage_gigabyte_hours
        FROM (
            SELECT cluster_id,
                cluster_alias,
                namespace,
                pod,
                usage_start,
                usage_end,
                persistentvolumeclaim,
                persistentvolume,
                storageclass,
                key,
                value,
                persistentvolumeclaim_capacity_bytes,
                persistentvolumeclaim_capacity_byte_seconds,
                volume_request_storage_byte_seconds,
                persistentvolumeclaim_usage_byte_seconds
            FROM reporting_ocpstoragelineitem_daily AS li,
                jsonb_each_text(li.persistentvolumeclaim_labels) persistentvolumeclaim_labels
        ) li
        WHERE usage_start >= '{start_date}'
            AND usage_start <= '{end_date}'
        GROUP BY li.cluster_id,
            li.cluster_alias,
            li.usage_start,
            li.usage_end,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            li.key,
            li.value
    ) t
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpstoragelineitem_daily_summary
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpstoragelineitem_daily_summary (
    cluster_id,
    cluster_alias,
    namespace,
    pod,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    usage_start,
    usage_end,
    persistentvolume_labels,
    persistentvolumeclaim_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_hours,
    volume_request_storage_gigabyte_hours,
    persistentvolumeclaim_usage_gigabyte_hours
)
    SELECT cluster_id,
        cluster_alias,
        namespace,
        pod,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        usage_start,
        usage_end,
        persistentvolume_labels,
        persistentvolumeclaim_labels,
        persistentvolumeclaim_capacity_gigabyte,
        persistentvolumeclaim_capacity_gigabyte_hours,
        volume_request_storage_gigabyte_hours,
        persistentvolumeclaim_usage_gigabyte_hours
    FROM reporting_ocpstoragelineitem_daily_summary_{uuid}
;