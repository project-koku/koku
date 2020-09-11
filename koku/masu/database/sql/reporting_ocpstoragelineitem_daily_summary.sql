CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}} AS (
    WITH cte_array_agg_keys AS (
        SELECT array_agg(key) as key_array
        FROM reporting_ocpenabledtagkeys
    ),
    cte_filtered_volume_labels AS (
        SELECT id,
            jsonb_object_agg(key,value) as volume_labels
        FROM (
            SELECT lid.id,
                -- persistentvolumeclaim_labels values will win in
                -- the volume label merge
                lid.persistentvolume_labels || lid.persistentvolumeclaim_labels as volume_labels,
                aak.key_array
            FROM reporting_ocpstoragelineitem_daily lid
            JOIN cte_array_agg_keys aak
                ON 1=1
            WHERE lid.usage_start >= {{start_date}}
                AND lid.usage_start <= {{end_date}}
                AND lid.cluster_id = {{cluster_id}}
                AND (
                    lid.persistentvolume_labels ?| aak.key_array
                    OR lid.persistentvolumeclaim_labels ?| aak.key_array
                )
        ) AS lid,
        jsonb_each_text(lid.volume_labels) AS labels
        WHERE key = ANY (key_array)
        GROUP BY id
    )
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
        coalesce(fvl.volume_labels, '{}'::jsonb) as volume_labels,
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
            * POWER(2, -30) as persistentvolumeclaim_usage_gigabyte_months,
        ab.provider_id as source_uuid
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily AS li
    LEFT JOIN cte_filtered_volume_labels AS fvl
        ON li.id = fvl.id
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
        fvl.volume_labels,
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
        persistentvolumeclaim_usage_gigabyte_months,
        source_uuid
    FROM reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}}
;

-- no need to wait on commit
TRUNCATE TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}};
DROP TABLE reporting_ocpstoragelineitem_daily_summary_{{uuid | sqlsafe}};
