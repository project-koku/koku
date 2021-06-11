#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update reporting summary tables."""
import datetime
import logging

from api.models import Provider
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor import enable_trino_processing
from masu.processor.aws.aws_report_parquet_summary_updater import AWSReportParquetSummaryUpdater
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.processor.azure.azure_report_parquet_summary_updater import AzureReportParquetSummaryUpdater
from masu.processor.azure.azure_report_summary_updater import AzureReportSummaryUpdater
from masu.processor.gcp.gcp_report_parquet_summary_updater import GCPReportParquetSummaryUpdater
from masu.processor.gcp.gcp_report_summary_updater import GCPReportSummaryUpdater
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater
from masu.processor.ocp.ocp_report_parquet_summary_updater import OCPReportParquetSummaryUpdater
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater

LOG = logging.getLogger(__name__)


class ReportSummaryUpdaterError(Exception):
    """Report Summary Updater Error."""

    pass


class ReportSummaryUpdaterCloudError(Exception):
    """Report Summary Updater Cloud Error."""

    pass


class ReportSummaryUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid, manifest_id=None):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider (str): The provider type.

        """
        self._schema = customer_schema
        self._provider_uuid = provider_uuid
        self._manifest = None
        if manifest_id is not None:
            with ReportManifestDBAccessor() as manifest_accessor:
                self._manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self._date_accessor = DateAccessor()
        with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
            self._provider = provider_accessor.get_provider()

        if not self._provider:
            raise ReportSummaryUpdaterError("Provider not found.")

        try:
            self._updater, self._ocp_cloud_updater = self._set_updater()
        except Exception as err:
            raise ReportSummaryUpdaterError(err)

        if not self._updater:
            raise ReportSummaryUpdaterError("Invalid provider type specified.")
        LOG.info("Starting report data summarization for provider uuid: %s.", self._provider.uuid)

    def _set_updater(self):
        """
        Create the report summary updater object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report summary updater

        """
        if self._provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            report_summary_updater = (
                AWSReportParquetSummaryUpdater
                if enable_trino_processing(
                    self._provider_uuid, self._provider.type, self._provider.customer.schema_name
                )
                else AWSReportSummaryUpdater
            )
        elif self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            report_summary_updater = (
                AzureReportParquetSummaryUpdater
                if enable_trino_processing(
                    self._provider_uuid, self._provider.type, self._provider.customer.schema_name
                )
                else AzureReportSummaryUpdater
            )
        elif self._provider.type in (Provider.PROVIDER_OCP,):
            report_summary_updater = (
                OCPReportParquetSummaryUpdater
                if enable_trino_processing(
                    self._provider_uuid, self._provider.type, self._provider.customer.schema_name
                )
                else OCPReportSummaryUpdater
            )
        elif self._provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            report_summary_updater = (
                GCPReportParquetSummaryUpdater
                if enable_trino_processing(
                    self._provider_uuid, self._provider.type, self._provider.customer.schema_name
                )
                else GCPReportSummaryUpdater
            )
        else:
            return (None, None)

        ocp_cloud_updater = (
            OCPCloudParquetReportSummaryUpdater
            if enable_trino_processing(self._provider_uuid, self._provider.type, self._provider.customer.schema_name)
            else OCPCloudReportSummaryUpdater
        )

        LOG.info(f"Set report_summary_updater = {report_summary_updater.__name__}")

        return (
            report_summary_updater(self._schema, self._provider, self._manifest),
            ocp_cloud_updater(self._schema, self._provider, self._manifest),
        )

    def _format_dates(self, start_date, end_date):
        """Convert dates to strings for use in the updater."""
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime("%Y-%m-%d")
        elif end_date is None:
            # Run up to the current date
            end_date = self._date_accessor.today_with_timezone("UTC")
            end_date = end_date.strftime("%Y-%m-%d")
        return start_date, end_date

    def update_daily_tables(self, start_date, end_date):
        """
        Update report daily rollup tables.

        Args:
            start_date (str, datetime): When to start.
            end_date (str, datetime): When to end.
            manifest_id (str): The particular manifest to use.

        Returns:
            (str, str): The start and end date strings used in the daily SQL.

        """
        start_date, end_date = self._format_dates(start_date, end_date)

        start_date, end_date = self._updater.update_daily_tables(start_date, end_date)

        invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)

        return start_date, end_date

    def update_summary_tables(self, start_date, end_date):
        """
        Update report summary tables.

        Args:
            start_date (str, datetime): When to start.
            end_date (str, datetime): When to end.
            manifest_id (str): The particular manifest to use.

        Returns:
            None

        """
        start_date, end_date = self._format_dates(start_date, end_date)
        LOG.info("Using start date: %s", start_date)
        LOG.info("Using end date: %s", end_date)

        start_date, end_date = self._updater.update_summary_tables(start_date, end_date)

        try:
            self._ocp_cloud_updater.update_summary_tables(start_date, end_date)
        except Exception as ex:
            raise ReportSummaryUpdaterCloudError(str(ex))

        invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
