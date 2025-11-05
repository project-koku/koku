/*
 * PostgreSQL-based OCP Data Aggregation
 * This SQL aggregates data from staging tables into daily summary tables.
 * Replaces Trino aggregation for on-premises deployments.
 */

CREATE OR REPLACE FUNCTION {{schema | sqlsafe}}.populate_daily_summary_from_staging(
    p_start_date date,
    p_end_date date,
    p_report_period_id integer,
    p_cluster_id varchar,
    p_cluster_alias varchar,
    p_source_uuid uuid
)
RETURNS TABLE(
    rows_inserted bigint,
    rows_deleted bigint
) AS $$
DECLARE
    v_enabled_keys text[];
    v_rows_inserted bigint := 0;
    v_rows_deleted bigint := 0;
BEGIN
    -- Get enabled tag keys for label filtering
    SELECT COALESCE(array_agg(key ORDER BY key), ARRAY[]::text[])
    INTO v_enabled_keys
    FROM {{schema | sqlsafe}}.reporting_enabledtagkeys
    WHERE enabled = true
      AND provider_type = 'OCP';

    -- Add VM label key if not present (always included)
    IF NOT ('vm_kubevirt_io_name' = ANY(v_enabled_keys)) THEN
        v_enabled_keys := array_prepend('vm_kubevirt_io_name', v_enabled_keys);
    END IF;

    -- Delete existing summary data for this date range
    -- Preserve infrastructure costs from OCP-on-Cloud matching
    DELETE FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary
    WHERE usage_start >= p_start_date
      AND usage_start <= p_end_date
      AND report_period_id = p_report_period_id
      AND source_uuid = p_source_uuid
      AND (infrastructure_usage_cost IS NULL OR infrastructure_usage_cost::text = '{}');

    GET DIAGNOSTICS v_rows_deleted = ROW_COUNT;

    -- Insert aggregated daily summary
    WITH enabled_keys AS (
        SELECT v_enabled_keys as keys
    ),
    -- Aggregate pod usage by day
    daily_pod_usage AS (
        SELECT
            date(interval_start) as usage_start,
            namespace,
            node,
            resource_id,
            -- Filter pod labels to enabled keys only
            CASE
                WHEN pod_labels IS NOT NULL THEN
                    (SELECT jsonb_object_agg(key, value)
                     FROM jsonb_each_text(pod_labels)
                     WHERE key = ANY(v_enabled_keys))
                ELSE NULL
            END as pod_labels,
            -- Convert seconds to hours
            SUM(pod_usage_cpu_core_seconds) / 3600.0 as pod_usage_cpu_core_hours,
            SUM(pod_request_cpu_core_seconds) / 3600.0 as pod_request_cpu_core_hours,
            SUM(COALESCE(pod_effective_usage_cpu_core_seconds, 0)) / 3600.0 as pod_effective_usage_cpu_core_hours,
            SUM(pod_limit_cpu_core_seconds) / 3600.0 as pod_limit_cpu_core_hours,
            -- Convert byte-seconds to gigabyte-hours
            SUM(pod_usage_memory_byte_seconds) / 3600.0 / 1073741824.0 as pod_usage_memory_gigabyte_hours,
            SUM(pod_request_memory_byte_seconds) / 3600.0 / 1073741824.0 as pod_request_memory_gigabyte_hours,
            SUM(COALESCE(pod_effective_usage_memory_byte_seconds, 0)) / 3600.0 / 1073741824.0 as pod_effective_usage_memory_gigabyte_hours,
            SUM(pod_limit_memory_byte_seconds) / 3600.0 / 1073741824.0 as pod_limit_memory_gigabyte_hours,
            -- Node capacity (take max per day per node)
            MAX(node_capacity_cpu_cores) as node_capacity_cpu_cores,
            MAX(node_capacity_cpu_core_seconds) / 3600.0 as node_capacity_cpu_core_hours,
            MAX(node_capacity_memory_bytes) / 1073741824.0 as node_capacity_memory_gigabytes,
            MAX(node_capacity_memory_byte_seconds) / 3600.0 / 1073741824.0 as node_capacity_memory_gigabyte_hours
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_pod_staging
        WHERE interval_start >= p_start_date
          AND interval_start < p_end_date + interval '1 day'
          AND report_period_id = p_report_period_id
          AND source_uuid = p_source_uuid
        GROUP BY date(interval_start), namespace, node, resource_id, pod_labels
    ),
    -- Aggregate storage usage by day
    daily_storage_usage AS (
        SELECT
            date(interval_start) as usage_start,
            namespace,
            node,
            persistentvolumeclaim,
            persistentvolume,
            storageclass,
            csi_volume_handle,
            -- Merge PV and PVC labels, filter to enabled keys
            CASE
                WHEN persistentvolume_labels IS NOT NULL OR persistentvolumeclaim_labels IS NOT NULL THEN
                    (SELECT jsonb_object_agg(key, value)
                     FROM (
                         SELECT key, value FROM jsonb_each_text(COALESCE(persistentvolume_labels, '{}'::jsonb))
                         UNION
                         SELECT key, value FROM jsonb_each_text(COALESCE(persistentvolumeclaim_labels, '{}'::jsonb))
                     ) labels
                     WHERE key = ANY(v_enabled_keys))
                ELSE NULL
            END as volume_labels,
            -- Convert to gigabytes
            MAX(persistentvolumeclaim_capacity_bytes) / 1073741824.0 as persistentvolumeclaim_capacity_gigabyte,
            -- Convert to gigabyte-months (daily data / days in month)
            SUM(persistentvolumeclaim_capacity_byte_seconds) / 3600.0 / 24.0 / 1073741824.0 /
                EXTRACT(day FROM (date_trunc('month', date(interval_start)) + interval '1 month' - interval '1 day'))::numeric
                as persistentvolumeclaim_capacity_gigabyte_months,
            SUM(volume_request_storage_byte_seconds) / 3600.0 / 24.0 / 1073741824.0 /
                EXTRACT(day FROM (date_trunc('month', date(interval_start)) + interval '1 month' - interval '1 day'))::numeric
                as volume_request_storage_gigabyte_months,
            SUM(persistentvolumeclaim_usage_byte_seconds) / 3600.0 / 24.0 / 1073741824.0 /
                EXTRACT(day FROM (date_trunc('month', date(interval_start)) + interval '1 month' - interval '1 day'))::numeric
                as persistentvolumeclaim_usage_gigabyte_months
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_storage_staging
        WHERE interval_start >= p_start_date
          AND interval_start < p_end_date + interval '1 day'
          AND report_period_id = p_report_period_id
          AND source_uuid = p_source_uuid
        GROUP BY date(interval_start), namespace, node, persistentvolumeclaim,
                 persistentvolume, storageclass, csi_volume_handle,
                 persistentvolume_labels, persistentvolumeclaim_labels
    ),
    -- Get node labels filtered by enabled keys (take most recent per day)
    node_labels_filtered AS (
        SELECT DISTINCT ON (date(interval_start), node)
            date(interval_start) as usage_start,
            node,
            CASE
                WHEN node_labels IS NOT NULL THEN
                    (SELECT jsonb_object_agg(key, value)
                     FROM jsonb_each_text(node_labels)
                     WHERE key = ANY(v_enabled_keys))
                ELSE NULL
            END as node_labels
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_node_labels_staging
        WHERE interval_start >= p_start_date
          AND interval_start < p_end_date + interval '1 day'
          AND report_period_id = p_report_period_id
          AND source_uuid = p_source_uuid
        ORDER BY date(interval_start), node, interval_start DESC
    ),
    -- Get namespace labels filtered by enabled keys (take most recent per day)
    namespace_labels_filtered AS (
        SELECT DISTINCT ON (date(interval_start), namespace)
            date(interval_start) as usage_start,
            namespace,
            CASE
                WHEN namespace_labels IS NOT NULL THEN
                    (SELECT jsonb_object_agg(key, value)
                     FROM jsonb_each_text(namespace_labels)
                     WHERE key = ANY(v_enabled_keys))
                ELSE NULL
            END as namespace_labels
        FROM {{schema | sqlsafe}}.reporting_ocpusagelineitem_namespace_labels_staging
        WHERE interval_start >= p_start_date
          AND interval_start < p_end_date + interval '1 day'
          AND report_period_id = p_report_period_id
          AND source_uuid = p_source_uuid
        ORDER BY date(interval_start), namespace, interval_start DESC
    ),
    -- Calculate cluster capacity (sum of all nodes per day)
    cluster_capacity AS (
        SELECT
            usage_start,
            SUM(node_capacity_cpu_core_hours) as cluster_capacity_cpu_core_hours,
            SUM(node_capacity_memory_gigabyte_hours) as cluster_capacity_memory_gigabyte_hours
        FROM daily_pod_usage
        GROUP BY usage_start
    )
    -- Main INSERT: Combine pod usage and storage usage
    INSERT INTO {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary (
        uuid,
        report_period_id,
        cluster_id,
        cluster_alias,
        data_source,
        usage_start,
        usage_end,
        namespace,
        node,
        resource_id,
        pod_labels,
        pod_usage_cpu_core_hours,
        pod_request_cpu_core_hours,
        pod_effective_usage_cpu_core_hours,
        pod_limit_cpu_core_hours,
        pod_usage_memory_gigabyte_hours,
        pod_request_memory_gigabyte_hours,
        pod_effective_usage_memory_gigabyte_hours,
        pod_limit_memory_gigabyte_hours,
        node_capacity_cpu_cores,
        node_capacity_cpu_core_hours,
        node_capacity_memory_gigabytes,
        node_capacity_memory_gigabyte_hours,
        cluster_capacity_cpu_core_hours,
        cluster_capacity_memory_gigabyte_hours,
        persistentvolumeclaim,
        persistentvolume,
        storageclass,
        volume_labels,
        persistentvolumeclaim_capacity_gigabyte,
        persistentvolumeclaim_capacity_gigabyte_months,
        volume_request_storage_gigabyte_months,
        persistentvolumeclaim_usage_gigabyte_months,
        source_uuid,
        csi_volume_handle,
        all_labels
    )
    SELECT
        gen_random_uuid() as uuid,
        p_report_period_id as report_period_id,
        p_cluster_id as cluster_id,
        p_cluster_alias as cluster_alias,
        CASE
            WHEN pod.namespace IS NOT NULL THEN 'Pod'
            WHEN stor.namespace IS NOT NULL THEN 'Storage'
        END as data_source,
        COALESCE(pod.usage_start, stor.usage_start) as usage_start,
        COALESCE(pod.usage_start, stor.usage_start) as usage_end,
        COALESCE(pod.namespace, stor.namespace) as namespace,
        COALESCE(pod.node, stor.node) as node,
        pod.resource_id,
        -- Merge pod labels with node labels and namespace labels
        -- Later labels override earlier ones (pod < node < namespace)
        COALESCE(pod.pod_labels, '{}'::jsonb) ||
        COALESCE(nl.node_labels, '{}'::jsonb) ||
        COALESCE(nsl.namespace_labels, '{}'::jsonb) as pod_labels,
        pod.pod_usage_cpu_core_hours,
        pod.pod_request_cpu_core_hours,
        pod.pod_effective_usage_cpu_core_hours,
        pod.pod_limit_cpu_core_hours,
        pod.pod_usage_memory_gigabyte_hours,
        pod.pod_request_memory_gigabyte_hours,
        pod.pod_effective_usage_memory_gigabyte_hours,
        pod.pod_limit_memory_gigabyte_hours,
        pod.node_capacity_cpu_cores,
        pod.node_capacity_cpu_core_hours,
        pod.node_capacity_memory_gigabytes,
        pod.node_capacity_memory_gigabyte_hours,
        cc.cluster_capacity_cpu_core_hours,
        cc.cluster_capacity_memory_gigabyte_hours,
        stor.persistentvolumeclaim,
        stor.persistentvolume,
        stor.storageclass,
        stor.volume_labels,
        stor.persistentvolumeclaim_capacity_gigabyte,
        stor.persistentvolumeclaim_capacity_gigabyte_months,
        stor.volume_request_storage_gigabyte_months,
        stor.persistentvolumeclaim_usage_gigabyte_months,
        p_source_uuid as source_uuid,
        stor.csi_volume_handle,
        -- Merge ALL labels for all_labels column
        COALESCE(pod.pod_labels, '{}'::jsonb) ||
        COALESCE(nl.node_labels, '{}'::jsonb) ||
        COALESCE(nsl.namespace_labels, '{}'::jsonb) ||
        COALESCE(stor.volume_labels, '{}'::jsonb) as all_labels
    FROM daily_pod_usage pod
    FULL OUTER JOIN daily_storage_usage stor
        ON pod.usage_start = stor.usage_start
        AND pod.namespace = stor.namespace
        AND pod.node = stor.node
    LEFT JOIN node_labels_filtered nl
        ON COALESCE(pod.usage_start, stor.usage_start) = nl.usage_start
        AND COALESCE(pod.node, stor.node) = nl.node
    LEFT JOIN namespace_labels_filtered nsl
        ON COALESCE(pod.usage_start, stor.usage_start) = nsl.usage_start
        AND COALESCE(pod.namespace, stor.namespace) = nsl.namespace
    LEFT JOIN cluster_capacity cc
        ON COALESCE(pod.usage_start, stor.usage_start) = cc.usage_start;

    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;

    -- Mark staging data as processed
    UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_pod_staging
    SET processed = true
    WHERE interval_start >= p_start_date
      AND interval_start < p_end_date + interval '1 day'
      AND report_period_id = p_report_period_id
      AND source_uuid = p_source_uuid
      AND processed = false;

    UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_storage_staging
    SET processed = true
    WHERE interval_start >= p_start_date
      AND interval_start < p_end_date + interval '1 day'
      AND report_period_id = p_report_period_id
      AND source_uuid = p_source_uuid
      AND processed = false;

    UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_node_labels_staging
    SET processed = true
    WHERE interval_start >= p_start_date
      AND interval_start < p_end_date + interval '1 day'
      AND report_period_id = p_report_period_id
      AND source_uuid = p_source_uuid
      AND processed = false;

    UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_namespace_labels_staging
    SET processed = true
    WHERE interval_start >= p_start_date
      AND interval_start < p_end_date + interval '1 day'
      AND report_period_id = p_report_period_id
      AND source_uuid = p_source_uuid
      AND processed = false;

    -- Return statistics
    RETURN QUERY SELECT v_rows_inserted, v_rows_deleted;

END;
$$ LANGUAGE plpgsql;
