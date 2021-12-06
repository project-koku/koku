#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update reporting summary tables."""
import datetime
import logging
from functools import cached_property

from api.common import log_json
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


class ReportSummaryUpdaterCloudError(ReportSummaryUpdaterError):
    """Report Summary Updater Cloud Error."""

    pass


class ReportSummaryUpdaterProviderNotFoundError(ReportSummaryUpdaterError):
    """Provider not found error"""

    pass


class ReportSummaryUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid, manifest_id=None, tracing_id=None):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider (str): The provider type.

        """
        self._schema = customer_schema
        self._provider_uuid = provider_uuid
        self._manifest = None
        self._tracing_id = tracing_id
        if manifest_id is not None:
            with ReportManifestDBAccessor() as manifest_accessor:
                self._manifest = manifest_accessor.get_manifest_by_id(manifest_id)
        self._date_accessor = DateAccessor()
        with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
            self._provider = provider_accessor.get_provider()

        if not self._provider:
            raise ReportSummaryUpdaterProviderNotFoundError(
                f"Provider data for uuid '{self._provider_uuid}' not found."
            )

        try:
            self._updater, self._ocp_cloud_updater = self._set_updater()
        except Exception as err:
            raise ReportSummaryUpdaterError(err)

        if not self._updater:
            raise ReportSummaryUpdaterError("Invalid provider type specified.")
        msg = f"Starting report data summarization for provider uuid: {self._provider.uuid}."
        LOG.info(log_json(self._tracing_id, msg))

    @cached_property
    def trino_enabled(self):
        """Return whether the source is enabled for Trino processing."""
        return enable_trino_processing(self._provider_uuid, self._provider.type, self._schema)

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
            report_summary_updater = AWSReportParquetSummaryUpdater if self.trino_enabled else AWSReportSummaryUpdater
        elif self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            report_summary_updater = (
                AzureReportParquetSummaryUpdater if self.trino_enabled else AzureReportSummaryUpdater
            )
        elif self._provider.type in (Provider.PROVIDER_OCP,):
            report_summary_updater = OCPReportParquetSummaryUpdater if self.trino_enabled else OCPReportSummaryUpdater
        elif self._provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            report_summary_updater = GCPReportParquetSummaryUpdater if self.trino_enabled else GCPReportSummaryUpdater
        else:
            return (None, None)

        ocp_cloud_updater = OCPCloudParquetReportSummaryUpdater if self.trino_enabled else OCPCloudReportSummaryUpdater

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

        Returns:
            (str, str): The start and end date strings used in the daily SQL.

        """
        msg = f"Daily summary starting for source {self._provider_uuid}"
        LOG.info(log_json(self._tracing_id, msg))
        start_date, end_date = self._format_dates(start_date, end_date)

        start_date, end_date = self._updater.update_daily_tables(start_date, end_date)

        invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
        msg = f"Daily summary completed for source {self._provider_uuid}"
        LOG.info(log_json(self._tracing_id, msg))
        return start_date, end_date

    def update_summary_tables(self, start_date, end_date, tracing_id):
        """
        Update report summary tables.

        Args:
            start_date (str, datetime): When to start.
            end_date (str, datetime): When to end.
            tracing_id (str): The tracing_id.

        Returns:
            None

        """
        msg = f"Summary processing starting for source {self._provider_uuid}"
        LOG.info(log_json(self._tracing_id, msg))
        start_date, end_date = self._format_dates(start_date, end_date)
        LOG.info(log_json(tracing_id, f"Using start date: {start_date}"))
        LOG.info(log_json(tracing_id, f"Using end date: {end_date}"))

        start_date, end_date = self._updater.update_summary_tables(start_date, end_date)

        try:
            if self._provider.type in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
                self._ocp_cloud_updater.update_summary_tables(start_date, end_date)
        except Exception as ex:
            raise ReportSummaryUpdaterCloudError(str(ex))

        msg = f"Summary processing completed for source {self._provider_uuid}"
        LOG.info(log_json(self._tracing_id, msg))

        invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
