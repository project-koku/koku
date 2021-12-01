#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider external interface for koku to consume."""
import logging

from dateutil.relativedelta import relativedelta

from api.common import log_json
from api.models import Provider
from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderNoFileError
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp_local.gcp_local_report_downloader import GCPLocalReportDownloader
from masu.external.downloader.ibm.ibm_report_downloader import IBMReportDownloader
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.downloader.report_downloader_base import ReportDownloaderError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from reporting_common.models import CostUsageReportStatus


LOG = logging.getLogger(__name__)


class ReportDownloader:
    """Interface for masu to use to get CUR accounts."""

    def __init__(
        self,
        customer_name,
        credentials,
        data_source,
        provider_type,
        provider_uuid,
        report_name=None,
        account=None,
        tracing_id="no_tracing_id",
    ):
        """Set the downloader based on the backend cloud provider."""
        self.customer_name = customer_name
        self.credentials = credentials
        self.data_source = data_source
        self.report_name = report_name
        self.provider_type = provider_type
        self.provider_uuid = provider_uuid
        self.tracing_id = tracing_id
        self.request_id = tracing_id  # TODO: Remove this once the downloaders have been updated
        self.account = account
        if self.account is None:
            self.account = customer_name[4:]
        self.context = {
            "tracing_id": self.tracing_id,
            "provider_uuid": self.provider_uuid,
            "provider_type": self.provider_type,
            "account": self.account,
        }

        try:
            self._downloader = self._set_downloader()
        except ReportDownloaderWarning as err:
            raise ReportDownloaderWarning(str(err))
        except Exception as err:
            raise ReportDownloaderError(str(err))

        if not self._downloader:
            raise ReportDownloaderError("Invalid provider type specified.")

    def _set_downloader(self):
        """
        Create the report downloader object.

        Downloader is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Some object that is a child of CURAccountsInterface

        """
        if self.provider_type == Provider.PROVIDER_AWS:
            return AWSReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                tracing_id=self.tracing_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_AWS_LOCAL:
            return AWSLocalReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                tracing_id=self.tracing_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_AZURE:
            return AzureReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_AZURE_LOCAL:
            return AzureLocalReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_OCP:
            return OCPReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_GCP:
            return GCPReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_GCP_LOCAL:
            return GCPLocalReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        if self.provider_type == Provider.PROVIDER_IBM:
            return IBMReportDownloader(
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                request_id=self.request_id,
                account=self.account,
                provider_type=self.provider_type,
            )
        return None

    def get_reports(self, number_of_months=2):
        """
        Download cost usage reports.

        Args:
            (Int) Number of monthly reports to download.

        Returns:
            (List) List of filenames downloaded.

        """
        reports = []
        try:
            current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)
            for month in reversed(range(number_of_months)):
                calculated_month = current_month + relativedelta(months=-month)
                reports += self.download_report(calculated_month)
        except Exception as err:
            raise ReportDownloaderError(str(err))
        return reports

    def is_report_processed(self, report_name, manifest_id):
        """Check if report_name has completed processing.

        Filter by the report name and then check the last_completed_datetime.
        If the date is not null, the report has been processed, and this method returns True.
        Otherwise returns False.

        """
        report_record = CostUsageReportStatus.objects.filter(manifest_id=manifest_id, report_name=report_name)
        if report_record:
            return report_record.filter(last_completed_datetime__isnull=False).exists()
        return False

    def download_manifest(self, date):
        """
        Download current manifest description for date.

        """
        return self._downloader.get_manifest_context_for_date(date)

    def download_report(self, report_context):
        """
        Download CUR for a given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ([{}]) List of dictionaries containing file path and compression.

        """
        date_time = report_context.get("date")
        msg = f"Attempting to get {self.provider_type} manifest for {str(date_time)}."
        LOG.info(log_json(self.tracing_id, msg, self.context))

        manifest_id = report_context.get("manifest_id")
        report = report_context.get("current_file")

        local_file_name = self._downloader.get_local_file_for_report(report)

        if self.is_report_processed(local_file_name, manifest_id):
            LOG.info(f"File has already been processed: {local_file_name}. Skipping...")
            return {}

        with ReportStatsDBAccessor(local_file_name, manifest_id) as stats_recorder:
            stored_etag = stats_recorder.get_etag()
            try:
                file_name, etag, _, split_files = self._downloader.download_file(
                    report, stored_etag, manifest_id=manifest_id, start_date=date_time
                )
                stats_recorder.update(etag=etag)
            except (AWSReportDownloaderNoFileError, AzureReportDownloaderError) as error:
                LOG.warning(f"Unable to download report file: {report}. Reason: {str(error)}")
                return {}

        # The create_table flag is used by the ParquetReportProcessor
        # to create a Hive/Trino table.
        return {
            "file": file_name,
            "split_files": split_files,
            "compression": report_context.get("compression"),
            "start_date": date_time,
            "assembly_id": report_context.get("assembly_id"),
            "manifest_id": manifest_id,
            "provider_uuid": self.provider_uuid,
            "create_table": report_context.get("create_table", False),
        }
