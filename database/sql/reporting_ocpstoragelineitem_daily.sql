CREATE TEMPORARY TABLE persistentvolume_labels_{uuid} AS (
    SELECT pl.cluster_id,
        pl.namespace,
        pl.pod,
        pl.persistentvolumeclaim,
        pl.persistentvolume,
        pl.storageclass,
        date(pl.interval_start) as usage_start,
        jsonb_object_agg(key, value) as persistentvolume_labels
    FROM (
        SELECT rp.cluster_id,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            ur.interval_start,
            key,
            value
        FROM (
            SELECT report_id,
                report_period_id,
                namespace,
                pod,
                persistentvolumeclaim,
                persistentvolume,
                storageclass,
                key,
                value
            FROM reporting_ocpstoragelineitem AS li,
                jsonb_each_text(li.persistentvolume_labels) labels
        ) li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
        GROUP BY rp.cluster_id,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            key,
            value,
            ur.interval_start
    ) pl
    GROUP BY pl.cluster_id,
        pl.namespace,
        pl.pod,
        pl.persistentvolumeclaim,
        pl.persistentvolume,
        pl.storageclass,
        date(pl.interval_start)
)
;

CREATE TEMPORARY TABLE persistentvolumeclaim_labels_{uuid} AS (
    SELECT pl.cluster_id,
        pl.namespace,
        pl.pod,
        pl.persistentvolumeclaim,
        pl.persistentvolume,
        pl.storageclass,
        date(pl.interval_start) as usage_start,
        jsonb_object_agg(key, value) as persistentvolumeclaim_labels
    FROM (
        SELECT rp.cluster_id,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            ur.interval_start,
            key,
            value
        FROM (
            SELECT report_id,
                report_period_id,
                namespace,
                pod,
                persistentvolumeclaim,
                persistentvolume,
                storageclass,
                key,
                value
            FROM reporting_ocpstoragelineitem AS li,
                jsonb_each_text(li.persistentvolumeclaim_labels) labels
        ) li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
        GROUP BY rp.cluster_id,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            key,
            value,
            ur.interval_start
    ) pl
    GROUP BY pl.cluster_id,
        pl.namespace,
        pl.pod,
        pl.persistentvolumeclaim,
        pl.persistentvolume,
        pl.storageclass,
        date(pl.interval_start)
)
;

CREATE TEMPORARY TABLE reporting_ocpstoragelineitem_daily_{uuid} AS (
    SELECT cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        namespace,
        pod,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        persistentvolume_labels,
        persistentvolumeclaim_labels,
        persistentvolumeclaim_capacity_byte_seconds,
        volume_request_storage_byte_seconds,
        persistentvolumeclaim_usage_byte_seconds,
        persistentvolumeclaim_capacity_bytes,
        total_seconds
    FROM (
        SELECT  rp.cluster_id,
            coalesce(max(p.name), rp.cluster_id) as cluster_alias,
            date(ur.interval_start) as usage_start,
            date(ur.interval_start) as usage_end,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            pvl.persistentvolume_labels,
            '{{}}'::jsonb as persistentvolumeclaim_labels,
            sum(li.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
            sum(li.volume_request_storage_byte_seconds) as volume_request_storage_byte_seconds,
            sum(li.persistentvolumeclaim_usage_byte_seconds) as persistentvolumeclaim_usage_byte_seconds,
            max(li.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
            count(ur.interval_start) * 3600 as total_seconds
        FROM reporting_ocpstoragelineitem AS li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        JOIN persistentvolume_labels_{uuid} as pvl
            ON rp.cluster_id = pvl.cluster_id
                AND li.namespace = pvl.namespace
                AND li.pod = pvl.pod
                AND date(ur.interval_start) = pvl.usage_start
        LEFT JOIN public.api_provider as p
            ON rp.provider_id = p.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
        GROUP BY rp.cluster_id,
            date(ur.interval_start),
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            pvl.persistentvolume_labels
    ) t

    UNION

    SELECT cluster_id,
        cluster_alias,
        usage_start,
        usage_end,
        namespace,
        pod,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        persistentvolume_labels,
        persistentvolumeclaim_labels,
        persistentvolumeclaim_capacity_byte_seconds,
        volume_request_storage_byte_seconds,
        persistentvolumeclaim_usage_byte_seconds,
        persistentvolumeclaim_capacity_bytes,
        total_seconds
    FROM (
        SELECT rp.cluster_id,
            coalesce(max(p.name), rp.cluster_id) as cluster_alias,
            date(ur.interval_start) as usage_start,
            date(ur.interval_start) as usage_end,
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            '{{}}'::jsonb as persistentvolume_labels,
            pvcl.persistentvolumeclaim_labels,
            sum(li.persistentvolumeclaim_capacity_byte_seconds) as persistentvolumeclaim_capacity_byte_seconds,
            sum(li.volume_request_storage_byte_seconds) as volume_request_storage_byte_seconds,
            sum(li.persistentvolumeclaim_usage_byte_seconds) as persistentvolumeclaim_usage_byte_seconds,
            max(li.persistentvolumeclaim_capacity_bytes) as persistentvolumeclaim_capacity_bytes,
            count(ur.interval_start) * 3600 as total_seconds
        FROM reporting_ocpstoragelineitem AS li
        JOIN reporting_ocpusagereport AS ur
            ON li.report_id = ur.id
        JOIN reporting_ocpusagereportperiod AS rp
            ON li.report_period_id = rp.id
        JOIN persistentvolumeclaim_labels_{uuid} as pvcl
            ON rp.cluster_id = pvcl.cluster_id
                AND li.namespace = pvcl.namespace
                AND li.pod = pvcl.pod
                AND date(ur.interval_start) = pvcl.usage_start
        LEFT JOIN public.api_provider as p
            ON rp.provider_id = p.id
        WHERE date(ur.interval_start) >= '{start_date}'
            AND date(ur.interval_start) <= '{end_date}'
        GROUP BY rp.cluster_id,
            date(ur.interval_start),
            li.namespace,
            li.pod,
            li.persistentvolumeclaim,
            li.persistentvolume,
            li.storageclass,
            pvcl.persistentvolumeclaim_labels
    ) t
)
;

-- Clear out old entries first
DELETE FROM reporting_ocpstoragelineitem_daily
WHERE usage_start >= '{start_date}'
    AND usage_start <= '{end_date}'
;

-- Populate the daily aggregate line item data
INSERT INTO reporting_ocpstoragelineitem_daily (
    cluster_id,
    cluster_alias,
    usage_start,
    usage_end,
    namespace,
    pod,
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
    FROM reporting_ocpstoragelineitem_daily_{uuid}
;
