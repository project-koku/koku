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
    WITH cte_node_inherited_labels AS (
        SELECT report_period_id,
            cluster_id,
            usage_start,
            namespace,
            node,
            persistentvolumeclaim,
            jsonb_object_agg(key, value) as persistentvolumeclaim_labels
        FROM (
            SELECT report_period_id,
                cluster_id,
                usage_start,
                namespace,
                node,
                persistentvolumeclaim,
                key,
                value
            FROM (
                SELECT li.report_period_id,
                    rp.cluster_id,
                    date(ur.interval_start) as usage_start,
                    li.namespace,
                    uli.node,
                    li.persistentvolumeclaim,
                    (li.persistentvolumeclaim_labels || coalesce(nlid.node_labels, '{}'::jsonb)) as persistentvolumeclaim_labels
                FROM {{schema | sqlsafe}}.reporting_ocpstoragelineitem AS li
                JOIN {{schema | sqlsafe}}.reporting_ocpusagereportperiod AS rp
                    ON li.report_period_id = rp.id
                JOIN {{schema | sqlsafe}}.reporting_ocpusagereport AS ur
                    ON li.report_id = ur.id
                LEFT JOIN volume_nodes_{{uuid | sqlsafe}} as uli
                    ON li.id = uli.id
                LEFT JOIN {{schema | sqlsafe}}.reporting_ocpnodelabellineitem_daily as nlid
                    ON uli.node = nlid.node
                        AND date(ur.interval_start) = nlid.usage_start
                        AND nlid.node_labels <> NULL
                WHERE date(ur.interval_start) >= {{start_date}}
                    AND date(ur.interval_start) <= {{end_date}}
                    AND rp.cluster_id = {{cluster_id}}
                GROUP BY li.report_period_id,
                    rp.cluster_id,
                    date(ur.interval_start),
                    li.namespace,
                    uli.node,
                    li.persistentvolumeclaim,
                    li.persistentvolumeclaim_labels,
                    nlid.node_labels
            ) AS nil,
            jsonb_each(nil.persistentvolumeclaim_labels) labels
        ) AS pl
        GROUP BY report_period_id,
            cluster_id,
            usage_start,
            namespace,
            node,
            persistentvolumeclaim
    )
    SELECT li.report_period_id,
        rp.cluster_id,
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
        (li.persistentvolumeclaim_labels || cte.persistentvolumeclaim_labels) as persistentvolumeclaim_labels,
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
    JOIN cte_node_inherited_labels as cte
        ON li.report_period_id = cte.report_period_id
            AND rp.cluster_id = cte.cluster_id
            AND date(ur.interval_start) = cte.usage_start
            AND li.namespace = cte.namespace
            AND li.persistentvolumeclaim = cte.persistentvolumeclaim
    WHERE date(ur.interval_start) >= {{start_date}}
        AND date(ur.interval_start) <= {{end_date}}
        AND rp.cluster_id = {{cluster_id}}
    GROUP BY li.report_period_id,
        rp.cluster_id,
        date(ur.interval_start),
        li.namespace,
        li.pod,
        li.persistentvolumeclaim,
        li.persistentvolume,
        li.storageclass,
        li.persistentvolume_labels,
        li.persistentvolumeclaim_labels,
        cte.persistentvolumeclaim_labels
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
    report_period_id,
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
    SELECT report_period_id,
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
    FROM reporting_ocpstoragelineitem_daily_{{uuid | sqlsafe}}
;
