#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Processor for OCP CSV files directly to PostgreSQL staging tables."""
import json
import logging
from datetime import datetime
from io import StringIO

import ciso8601
import pandas as pd
from django.conf import settings
from django.db import connection
from django_tenants.utils import schema_context

from api.common import log_json
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.external.kafka_msg_handler import EmptyPayloadFileError
from masu.util.common import month_date_range
from masu.util.ocp import common as utils
from reporting.provider.ocp.models import OCPUsageReportPeriod

LOG = logging.getLogger(__name__)


class OCPPostgresReportProcessor:
    """Process OCP CSV files directly into PostgreSQL staging tables."""

    # Map report types to staging table names
    STAGING_TABLE_MAP = {
        "pod_usage": "reporting_ocpusagelineitem_pod_staging",
        "storage_usage": "reporting_ocpusagelineitem_storage_staging",
        "node_labels": "reporting_ocpusagelineitem_node_labels_staging",
        "namespace_labels": "reporting_ocpusagelineitem_namespace_labels_staging",
        "vm_usage": "reporting_ocpusagelineitem_vm_staging",
    }

    def __init__(self, manifest_id, account, s3_path, provider_uuid, local_path, report_type):
        """Initialize the processor.

        Args:
            manifest_id (int): Manifest ID
            account (str): Account/schema name
            s3_path (str): S3 path to CSV file
            provider_uuid (UUID): Provider UUID
            local_path (str): Local path to CSV file
            report_type (str): Type of report (pod_usage, storage_usage, etc.)
        """
        self._manifest_id = manifest_id
        self._account = account
        self._s3_path = s3_path
        self._provider_uuid = provider_uuid
        self._local_path = local_path
        self._report_type = report_type
        self._schema = f"acct{account}"
        self._enabled_keys = None

    def _get_provider(self):
        """Get provider object."""
        from reporting.provider.models import Provider

        return Provider.objects.get(uuid=self._provider_uuid)

    def _get_enabled_tag_keys(self):
        """Get enabled tag keys for label filtering."""
        if self._enabled_keys is not None:
            return self._enabled_keys

        with schema_context(self._schema):
            with OCPReportDBAccessor(self._schema) as accessor:
                enabled_tags = accessor.get_enabled_tags()
                self._enabled_keys = {tag.key for tag in enabled_tags if tag.provider_type == "OCP"}

        # Always include VM label key
        self._enabled_keys.add("vm_kubevirt_io_name")

        LOG.info(
            log_json(
                msg="loaded enabled tag keys",
                schema=self._schema,
                provider_uuid=self._provider_uuid,
                num_keys=len(self._enabled_keys),
            )
        )
        return self._enabled_keys

    def _filter_labels(self, labels_json):
        """Filter labels to only include enabled keys.

        Args:
            labels_json (str): JSON string of labels

        Returns:
            str: JSON string of filtered labels
        """
        if not labels_json or pd.isna(labels_json):
            return None

        try:
            labels = json.loads(labels_json) if isinstance(labels_json, str) else labels_json
            if not labels:
                return None

            enabled_keys = self._get_enabled_tag_keys()
            filtered = {k: v for k, v in labels.items() if k in enabled_keys}

            return json.dumps(filtered) if filtered else None
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            LOG.warning(
                log_json(
                    msg="error filtering labels",
                    error=str(e),
                    labels=str(labels_json)[:100],  # Log first 100 chars
                )
            )
            return None

    def _calculate_effective_usage(self, df):
        """Calculate effective usage (min of usage and request).

        Args:
            df (DataFrame): Pod usage dataframe

        Returns:
            DataFrame: Dataframe with effective usage columns added
        """
        if "pod_usage_cpu_core_seconds" in df.columns and "pod_request_cpu_core_seconds" in df.columns:
            df["pod_effective_usage_cpu_core_seconds"] = df[
                ["pod_usage_cpu_core_seconds", "pod_request_cpu_core_seconds"]
            ].min(axis=1, skipna=True)

        if "pod_usage_memory_byte_seconds" in df.columns and "pod_request_memory_byte_seconds" in df.columns:
            df["pod_effective_usage_memory_byte_seconds"] = df[
                ["pod_usage_memory_byte_seconds", "pod_request_memory_byte_seconds"]
            ].min(axis=1, skipna=True)

        return df

    def _process_label_columns(self, df, label_columns):
        """Filter labels in dataframe columns.

        Args:
            df (DataFrame): Dataframe containing label columns
            label_columns (list): List of label column names

        Returns:
            DataFrame: Dataframe with filtered labels
        """
        for col in label_columns:
            if col in df.columns:
                df[col] = df[col].apply(self._filter_labels)

        return df

    def _read_csv(self):
        """Read CSV file with pandas.

        Returns:
            DataFrame: Pandas dataframe with CSV data

        Raises:
            EmptyPayloadFileError: If CSV file is empty
        """
        try:
            df = pd.read_csv(
                self._local_path,
                dtype=pd.StringDtype(storage="pyarrow"),
                on_bad_lines="warn",
            )

            if df.empty:
                raise EmptyPayloadFileError("CSV file is empty")

            LOG.info(
                log_json(
                    msg="CSV file read successfully",
                    schema=self._schema,
                    provider_uuid=self._provider_uuid,
                    report_type=self._report_type,
                    rows=len(df),
                    columns=len(df.columns),
                )
            )
            return df

        except pd.errors.EmptyDataError as e:
            raise EmptyPayloadFileError("CSV file is empty") from e
        except Exception as e:
            LOG.error(
                log_json(
                    msg="error reading CSV file",
                    schema=self._schema,
                    provider_uuid=self._provider_uuid,
                    error=str(e),
                    path=self._local_path,
                )
            )
            raise

    def _add_metadata_columns(self, df, report_period_id):
        """Add metadata columns to dataframe.

        Args:
            df (DataFrame): Source dataframe
            report_period_id (int): Report period ID

        Returns:
            DataFrame: Dataframe with metadata columns added
        """
        df["report_period_id"] = report_period_id
        df["source_uuid"] = str(self._provider_uuid)
        df["processed"] = False
        return df

    def _bulk_copy_to_staging(self, df, table_name):
        """Use PostgreSQL COPY for fast bulk insert.

        Args:
            df (DataFrame): Data to insert
            table_name (str): Target staging table name
        """
        buffer = StringIO()

        # Write dataframe to buffer as CSV
        df.to_csv(buffer, index=False, header=False, sep="\t", na_rep="\\N")
        buffer.seek(0)

        # Use COPY command for fast bulk insert
        full_table_name = f"{self._schema}.{table_name}"

        with connection.cursor() as cursor:
            cursor.copy_expert(
                f"COPY {full_table_name} FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')",
                buffer,
            )

        LOG.info(
            log_json(
                msg="bulk copied data to staging table",
                schema=self._schema,
                table=table_name,
                rows=len(df),
            )
        )

    def create_bill(self, bill_date):
        """Create bill/report period entry in PostgreSQL.

        Args:
            bill_date (str|datetime): Bill date

        Returns:
            OCPUsageReportPeriod: Report period object
        """
        if isinstance(bill_date, str):
            bill_date = ciso8601.parse_datetime(bill_date)

        report_date_range = month_date_range(bill_date)
        start_date, end_date = report_date_range.split("-")

        report_period_start = ciso8601.parse_datetime(start_date).replace(hour=0, minute=0, tzinfo=settings.UTC)
        report_period_end = ciso8601.parse_datetime(end_date).replace(hour=0, minute=0, tzinfo=settings.UTC)
        # Make end date first of next month
        report_period_end = report_period_end + datetime.timedelta(days=1)

        provider = self._get_provider()

        cluster_id = utils.get_cluster_id_from_provider(provider.uuid)
        cluster_alias = utils.get_cluster_alias_from_cluster_id(cluster_id)

        with schema_context(self._schema):
            report_period, created = OCPUsageReportPeriod.objects.get_or_create(
                cluster_id=cluster_id,
                report_period_start=report_period_start,
                report_period_end=report_period_end,
                provider=provider,
                defaults={"cluster_alias": cluster_alias},
            )

            if created:
                LOG.info(
                    log_json(
                        msg="created report period",
                        schema=self._schema,
                        cluster_id=cluster_id,
                        report_period_id=report_period.id,
                        report_period_start=str(report_period_start),
                        report_period_end=str(report_period_end),
                    )
                )

        return report_period

    def process(self):
        """Process CSV file into staging tables.

        Returns:
            bool: True if processing was successful
        """
        LOG.info(
            log_json(
                msg="starting PostgreSQL-based OCP CSV processing",
                schema=self._schema,
                provider_uuid=self._provider_uuid,
                report_type=self._report_type,
                manifest_id=self._manifest_id,
                s3_path=self._s3_path,
            )
        )

        try:
            # Read CSV file
            df = self._read_csv()

            # Get or create report period from first row
            first_row = df.iloc[0]
            bill_date = pd.to_datetime(first_row.get("report_period_start", first_row.get("interval_start")))
            report_period = self.create_bill(bill_date)

            # Add metadata columns
            df = self._add_metadata_columns(df, report_period.id)

            # Process based on report type
            if self._report_type == "pod_usage":
                # Calculate effective usage
                df = self._calculate_effective_usage(df)
                # Filter pod labels
                df = self._process_label_columns(df, ["pod_labels"])

            elif self._report_type == "storage_usage":
                # Filter storage labels
                df = self._process_label_columns(df, ["persistentvolume_labels", "persistentvolumeclaim_labels"])

            elif self._report_type == "node_labels":
                # Filter node labels
                df = self._process_label_columns(df, ["node_labels"])

            elif self._report_type == "namespace_labels":
                # Filter namespace labels
                df = self._process_label_columns(df, ["namespace_labels"])

            elif self._report_type == "vm_usage":
                # No special processing needed for VM usage
                pass

            else:
                LOG.warning(
                    log_json(
                        msg="unknown report type",
                        report_type=self._report_type,
                    )
                )

            # Get staging table name
            staging_table = self.STAGING_TABLE_MAP.get(self._report_type)
            if not staging_table:
                raise ValueError(f"Unknown report type: {self._report_type}")

            # Bulk insert into staging table
            with schema_context(self._schema):
                self._bulk_copy_to_staging(df, staging_table)

            LOG.info(
                log_json(
                    msg="PostgreSQL-based OCP CSV processing completed",
                    schema=self._schema,
                    provider_uuid=self._provider_uuid,
                    report_type=self._report_type,
                    rows_processed=len(df),
                )
            )

            return True

        except EmptyPayloadFileError:
            LOG.warning(
                log_json(
                    msg="empty CSV file, skipping",
                    schema=self._schema,
                    provider_uuid=self._provider_uuid,
                    report_type=self._report_type,
                )
            )
            return True  # Not an error, just skip

        except Exception as e:
            LOG.error(
                log_json(
                    msg="error processing OCP CSV file",
                    schema=self._schema,
                    provider_uuid=self._provider_uuid,
                    report_type=self._report_type,
                    error=str(e),
                )
            )
            raise
