CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    SELECT uuid_generate_v4() as uuid,
        li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.namespace,
        li.node,
        li.usage_start,
        li.usage_end,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels || li.persistentvolumeclaim_labels as volume_labels,
        max(li.persistentvolumeclaim_capacity_bytes) * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte,
        sum(li.persistentvolumeclaim_capacity_byte_seconds) /
            (86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day'))
            * POWER(2, -30) as persistentvolumeclaim_capacity_gigabyte_months,
        sum(li.volume_request_storage_byte_seconds) /
            (86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day'))
            * POWER(2, -30) as volume_request_storage_gigabyte_months,
        sum(li.persistentvolumeclaim_usage_byte_seconds) /
            (86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day'))
            * POWER(2, -30) as persistentvolumeclaim_usage_gigabyte_months,
        ab.provider_id as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod as ab
        ON li.cluster_id = ab.cluster_id
    WHERE usage_start >= {{start_date}}
        AND usage_start <= {{end_date}}
        AND li.cluster_id = {{cluster_id}}
    GROUP BY li.report_period_id,
        li.cluster_id,
        li.cluster_alias,
        li.usage_start,
        li.usage_end,
        li.namespace,
        li.node,
        li.persistentvolume_labels || li.persistentvolumeclaim_labels,
        li.persistentvolume,
        li.persistentvolumeclaim,
        li.storageclass,
        ab.provider_id
)
;

DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
    AND data_source = 'Storage'
;

-- Populate the daily aggregate line item data
-- THIS IS A PARTITONED TABLE
INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
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
    usage_start,
    usage_end,
    volume_labels,
    persistentvolumeclaim_capacity_gigabyte,
    persistentvolumeclaim_capacity_gigabyte_months,
    volume_request_storage_gigabyte_months,
    persistentvolumeclaim_usage_gigabyte_months,
    source_uuid
)
    SELECT uuid,
        report_period_id,
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
        persistentvolumeclaim_usage_gigabyte_months,
        source_uuid
    FROM reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}}
;

-- no need to wait on commit
TRUNCATE TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}};
