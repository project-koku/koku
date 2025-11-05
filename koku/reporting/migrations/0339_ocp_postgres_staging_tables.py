#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Create PostgreSQL staging tables for OCP data."""
from django.db import migrations


class Migration(migrations.Migration):
    """Create staging tables for PostgreSQL-based OCP pipeline."""

    dependencies = [
        ("reporting", "0338_ocpnode_architecture"),
    ]

    operations = [
        # Create pod usage staging table (partitioned)
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS reporting_ocpusagelineitem_pod_staging (
                id BIGSERIAL,
                report_period_start date,
                report_period_end date,
                interval_start timestamp NOT NULL,
                interval_end timestamp,
                namespace varchar(253),
                pod varchar(253),
                node varchar(253),
                resource_id varchar(253),
                pod_usage_cpu_core_seconds numeric(24,6),
                pod_request_cpu_core_seconds numeric(24,6),
                pod_effective_usage_cpu_core_seconds numeric(24,6),
                pod_limit_cpu_core_seconds numeric(24,6),
                pod_usage_memory_byte_seconds numeric(24,6),
                pod_request_memory_byte_seconds numeric(24,6),
                pod_effective_usage_memory_byte_seconds numeric(24,6),
                pod_limit_memory_byte_seconds numeric(24,6),
                node_capacity_cpu_cores numeric(24,6),
                node_capacity_cpu_core_seconds numeric(24,6),
                node_capacity_memory_bytes numeric(24,6),
                node_capacity_memory_byte_seconds numeric(24,6),
                pod_labels jsonb,
                node_role varchar(50),
                report_period_id integer NOT NULL,
                source_uuid uuid NOT NULL,
                processed boolean DEFAULT false,
                PRIMARY KEY (id, interval_start)
            ) PARTITION BY RANGE (interval_start);

            CREATE INDEX IF NOT EXISTS pod_staging_interval_start_idx
                ON reporting_ocpusagelineitem_pod_staging (interval_start);
            CREATE INDEX IF NOT EXISTS pod_staging_source_uuid_idx
                ON reporting_ocpusagelineitem_pod_staging (source_uuid);
            CREATE INDEX IF NOT EXISTS pod_staging_report_period_id_idx
                ON reporting_ocpusagelineitem_pod_staging (report_period_id);
            CREATE INDEX IF NOT EXISTS pod_staging_namespace_idx
                ON reporting_ocpusagelineitem_pod_staging (namespace varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS pod_staging_node_idx
                ON reporting_ocpusagelineitem_pod_staging (node varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS pod_staging_processed_idx
                ON reporting_ocpusagelineitem_pod_staging (processed) WHERE processed = false;
            """,
            reverse_sql="DROP TABLE IF EXISTS reporting_ocpusagelineitem_pod_staging CASCADE;",
        ),
        # Create storage usage staging table (partitioned)
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS reporting_ocpusagelineitem_storage_staging (
                id BIGSERIAL,
                report_period_start date,
                report_period_end date,
                interval_start timestamp NOT NULL,
                interval_end timestamp,
                namespace varchar(253),
                pod varchar(253),
                node varchar(253),
                persistentvolumeclaim varchar(253),
                persistentvolume varchar(253),
                storageclass varchar(253),
                persistentvolumeclaim_capacity_bytes numeric(24,6),
                persistentvolumeclaim_capacity_byte_seconds numeric(24,6),
                volume_request_storage_byte_seconds numeric(24,6),
                persistentvolumeclaim_usage_byte_seconds numeric(24,6),
                persistentvolume_labels jsonb,
                persistentvolumeclaim_labels jsonb,
                csi_driver varchar(253),
                csi_volume_handle varchar(253),
                report_period_id integer NOT NULL,
                source_uuid uuid NOT NULL,
                processed boolean DEFAULT false,
                PRIMARY KEY (id, interval_start)
            ) PARTITION BY RANGE (interval_start);

            CREATE INDEX IF NOT EXISTS storage_staging_interval_start_idx
                ON reporting_ocpusagelineitem_storage_staging (interval_start);
            CREATE INDEX IF NOT EXISTS storage_staging_source_uuid_idx
                ON reporting_ocpusagelineitem_storage_staging (source_uuid);
            CREATE INDEX IF NOT EXISTS storage_staging_report_period_id_idx
                ON reporting_ocpusagelineitem_storage_staging (report_period_id);
            CREATE INDEX IF NOT EXISTS storage_staging_namespace_idx
                ON reporting_ocpusagelineitem_storage_staging (namespace varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS storage_staging_node_idx
                ON reporting_ocpusagelineitem_storage_staging (node varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS storage_staging_pvc_idx
                ON reporting_ocpusagelineitem_storage_staging (persistentvolumeclaim varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS storage_staging_processed_idx
                ON reporting_ocpusagelineitem_storage_staging (processed) WHERE processed = false;
            """,
            reverse_sql="DROP TABLE IF EXISTS reporting_ocpusagelineitem_storage_staging CASCADE;",
        ),
        # Create node labels staging table (partitioned)
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS reporting_ocpusagelineitem_node_labels_staging (
                id BIGSERIAL,
                report_period_start date,
                report_period_end date,
                interval_start timestamp NOT NULL,
                interval_end timestamp,
                node varchar(253),
                node_labels jsonb,
                report_period_id integer NOT NULL,
                source_uuid uuid NOT NULL,
                processed boolean DEFAULT false,
                PRIMARY KEY (id, interval_start)
            ) PARTITION BY RANGE (interval_start);

            CREATE INDEX IF NOT EXISTS node_labels_staging_interval_start_idx
                ON reporting_ocpusagelineitem_node_labels_staging (interval_start);
            CREATE INDEX IF NOT EXISTS node_labels_staging_source_uuid_idx
                ON reporting_ocpusagelineitem_node_labels_staging (source_uuid);
            CREATE INDEX IF NOT EXISTS node_labels_staging_report_period_id_idx
                ON reporting_ocpusagelineitem_node_labels_staging (report_period_id);
            CREATE INDEX IF NOT EXISTS node_labels_staging_node_idx
                ON reporting_ocpusagelineitem_node_labels_staging (node varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS node_labels_staging_processed_idx
                ON reporting_ocpusagelineitem_node_labels_staging (processed) WHERE processed = false;
            """,
            reverse_sql="DROP TABLE IF EXISTS reporting_ocpusagelineitem_node_labels_staging CASCADE;",
        ),
        # Create namespace labels staging table (partitioned)
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS reporting_ocpusagelineitem_namespace_labels_staging (
                id BIGSERIAL,
                report_period_start date,
                report_period_end date,
                interval_start timestamp NOT NULL,
                interval_end timestamp,
                namespace varchar(253),
                namespace_labels jsonb,
                report_period_id integer NOT NULL,
                source_uuid uuid NOT NULL,
                processed boolean DEFAULT false,
                PRIMARY KEY (id, interval_start)
            ) PARTITION BY RANGE (interval_start);

            CREATE INDEX IF NOT EXISTS namespace_labels_staging_interval_start_idx
                ON reporting_ocpusagelineitem_namespace_labels_staging (interval_start);
            CREATE INDEX IF NOT EXISTS namespace_labels_staging_source_uuid_idx
                ON reporting_ocpusagelineitem_namespace_labels_staging (source_uuid);
            CREATE INDEX IF NOT EXISTS namespace_labels_staging_report_period_id_idx
                ON reporting_ocpusagelineitem_namespace_labels_staging (report_period_id);
            CREATE INDEX IF NOT EXISTS namespace_labels_staging_namespace_idx
                ON reporting_ocpusagelineitem_namespace_labels_staging (namespace varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS namespace_labels_staging_processed_idx
                ON reporting_ocpusagelineitem_namespace_labels_staging (processed) WHERE processed = false;
            """,
            reverse_sql="DROP TABLE IF EXISTS reporting_ocpusagelineitem_namespace_labels_staging CASCADE;",
        ),
        # Create VM usage staging table (partitioned)
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS reporting_ocpusagelineitem_vm_staging (
                id BIGSERIAL,
                report_period_start date,
                report_period_end date,
                interval_start timestamp NOT NULL,
                interval_end timestamp,
                namespace varchar(253),
                node varchar(253),
                resource_id varchar(253),
                vm_uptime_total_seconds numeric(24,6),
                vm_cpu_limit_cores numeric(24,6),
                vm_cpu_limit_core_seconds numeric(24,6),
                vm_cpu_request_cores numeric(24,6),
                vm_cpu_request_core_seconds numeric(24,6),
                vm_cpu_usage_total_seconds numeric(24,6),
                vm_memory_limit_bytes numeric(24,6),
                vm_memory_limit_byte_seconds numeric(24,6),
                vm_memory_request_bytes numeric(24,6),
                vm_memory_request_byte_seconds numeric(24,6),
                vm_memory_usage_byte_seconds numeric(24,6),
                vm_disk_allocated_size_byte_seconds numeric(24,6),
                report_period_id integer NOT NULL,
                source_uuid uuid NOT NULL,
                processed boolean DEFAULT false,
                PRIMARY KEY (id, interval_start)
            ) PARTITION BY RANGE (interval_start);

            CREATE INDEX IF NOT EXISTS vm_staging_interval_start_idx
                ON reporting_ocpusagelineitem_vm_staging (interval_start);
            CREATE INDEX IF NOT EXISTS vm_staging_source_uuid_idx
                ON reporting_ocpusagelineitem_vm_staging (source_uuid);
            CREATE INDEX IF NOT EXISTS vm_staging_report_period_id_idx
                ON reporting_ocpusagelineitem_vm_staging (report_period_id);
            CREATE INDEX IF NOT EXISTS vm_staging_namespace_idx
                ON reporting_ocpusagelineitem_vm_staging (namespace varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS vm_staging_node_idx
                ON reporting_ocpusagelineitem_vm_staging (node varchar_pattern_ops);
            CREATE INDEX IF NOT EXISTS vm_staging_processed_idx
                ON reporting_ocpusagelineitem_vm_staging (processed) WHERE processed = false;
            """,
            reverse_sql="DROP TABLE IF EXISTS reporting_ocpusagelineitem_vm_staging CASCADE;",
        ),
    ]
