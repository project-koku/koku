CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_shared_volume_node_count AS (
        SELECT li.report_period_id,
            li.usage_start,
            li.persistentvolume,
            CASE WHEN li.node_count = 0 THEN 1
                ELSE li.node_count
            END as node_count
        FROM (
            SELECT li.report_period_id,
                li.usage_start,
                li.persistentvolume,
                count(DISTINCT li.node) as node_count
            FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li
            WHERE usage_start >= {{start_date}}
                AND usage_start <= {{end_date}}
                AND li.cluster_id = {{cluster_id}}
            GROUP BY li.report_period_id,
                li.usage_start,
                li.persistentvolume
        ) AS li
    )
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
        -- Divide volume usage and requests by the number of nodes that volume is mounted on
        sum(li.volume_request_storage_byte_seconds) /
            (86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day'))
            * POWER(2, -30)
            / max(nc.node_count) as volume_request_storage_gigabyte_months,
        sum(li.persistentvolumeclaim_usage_byte_seconds) /
            (86400 *
            extract(days FROM date_trunc('month', li.usage_start) + interval '1 month - 1 day'))
            * POWER(2, -30)
            / max(nc.node_count) as persistentvolumeclaim_usage_gigabyte_months,
        {{source_uuid}} as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li
    JOIN cte_shared_volume_node_count AS nc
        ON li.usage_start = nc.usage_start
            AND li.persistentvolume = nc.persistentvolume
            AND li.report_period_id = nc.report_period_id
    WHERE li.usage_start >= {{start_date}}
        AND li.usage_start <= {{end_date}}
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
        li.storageclass
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
