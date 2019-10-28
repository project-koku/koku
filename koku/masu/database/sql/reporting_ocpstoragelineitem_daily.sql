CREATE TEMPORARY TABLE volume_nodes_{{uuid | sqlsafe}} AS (
    SELECT li.id,
        uli.node
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem as li
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    LEFT JOIN {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily as uli
        ON li.pod = uli.pod
            AND li.namespace = uli.namespace
            AND rp.cluster_id = uli.cluster_id
    GROUP BY li.id, uli.node
)
;

CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}} AS (
    SELECT  rp.cluster_id,
        coalesce(max(p.name), rp.cluster_id) as cluster_alias,
        date(ur.interval_start) as usage_start,
        date(ur.interval_start) as usage_end,
        li.namespace,
        li.pod,
        max(uli.node) as node,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels,
        sum(li.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
        sum(li.volume_request_storage_byte_seconds) as volume_request_storage_byte_seconds,
        sum(li.persistentvolumeclaim_usage_byte_seconds) as persistentvolumeclaim_usage_byte_seconds,
        max(li.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
        count(ur.interval_start) * 3600 as total_seconds
    FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem AS li
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereport AS ur
        ON li.report_id = ur.id
    JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
        ON li.report_period_id = rp.id
    LEFT JOIN public.api_provider as p
        ON rp.provider_id = p.uuid
    LEFT JOIN volume_nodes_{{uuid | sqlsafe}} as uli
        ON li.id = uli.id
    WHERE date(ur.interval_start) >= {{start_date}}
        AND date(ur.interval_start) <= {{end_date}}
        AND rp.cluster_id = {{cluster_id}}
    GROUP BY rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels
)
;

-- Clear out old entries first
DELETE FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily
WHERE usage_start >= {{start_date}}
    AND usage_start <= {{end_date}}
    AND cluster_id = {{cluster_id}}
;

-- Populate the daily aggregate line item data
INSERT INTO {{schema | sqlsafe}}.reporting_ocpstoragelineitem_daily (
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    pod,
    node,
    persistentvolume_labels,
    persistentvolumeclaim_labels,
    persistentvolumeclaim,
    persistentvolume,
    storageclass,
    persistentvolumeclaim_capacity_bytes,
    persistentvolumeclaim_capacity_byte_seconds,
    volume_request_storage_byte_seconds,
    persistentvolumeclaim_usage_byte_seconds,
    total_seconds
)
    SELECT cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        namespace,
        pod,
        node,
        persistentvolume_labels,
        persistentvolumeclaim_labels,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        persistentvolumeclaim_capacity_bytes,
        persistentvolumeclaim_capacity_byte_seconds,
        volume_request_storage_byte_seconds,
        persistentvolumeclaim_usage_byte_seconds,
        total_seconds
    FROM reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}}
;
