#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider external interface for koku to consume."""
import logging

from api.common import log_json
from api.provider.models import Provider
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderNoFileError
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.gcp_local.gcp_local_report_downloader import GCPLocalReportDownloader
from masu.external.downloader.report_downloader_base import ReportDownloaderError
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
from masu.util.aws.common import UploadError
from masu.util.common import CreateDailyArchivesError
from reporting_common.models import CombinedChoices
from reporting_common.models import CostUsageReportStatus
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep

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
        ingress_reports=None,
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
        self.ingress_reports = ingress_reports
        if self.account is None:
            # Existing schema will start with acct and we strip that prefix for use later
            # new customers include the org prefix in case an org-id and an account number might overlap
            self.account = customer_name.strip("acct")
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
        downloader_map = {
            Provider.PROVIDER_AWS: AWSReportDownloader,
            Provider.PROVIDER_AWS_LOCAL: AWSLocalReportDownloader,
            Provider.PROVIDER_AZURE: AzureReportDownloader,
            Provider.PROVIDER_AZURE_LOCAL: AzureLocalReportDownloader,
            Provider.PROVIDER_GCP: GCPReportDownloader,
            Provider.PROVIDER_GCP_LOCAL: GCPLocalReportDownloader,
        }
        if self.provider_type in downloader_map:
            return downloader_map[self.provider_type](
                customer_name=self.customer_name,
                credentials=self.credentials,
                data_source=self.data_source,
                report_name=self.report_name,
                provider_uuid=self.provider_uuid,
                tracing_id=self.tracing_id,
                account=self.account,
                provider_type=self.provider_type,
                ingress_reports=self.ingress_reports,
            )
        return None

    def is_report_processed(self, report_name, manifest_id):
        """Check if report_name has completed processing.

        Filter by the report name and then check the completed_datetime.
        If the date is not null, the report has been processed, and this method returns True.
        Otherwise returns False.

        """
        return CostUsageReportStatus.objects.filter(
            manifest_id=manifest_id,
            report_name=report_name,
            completed_datetime__isnull=False,
        ).exists()

    def download_manifest(self, date):
        """
        Download current manifest description for date.

        """
        manifest = self._downloader.get_manifest_context_for_date(date)
        if not manifest:
            return []
        if not isinstance(manifest, list):
            manifest = [manifest]
        return manifest

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
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        manifest_id = report_context.get("manifest_id")
        report = report_context.get("current_file")

        local_file_name = self._downloader.get_local_file_for_report(report)

        if self.is_report_processed(local_file_name, manifest_id):
            LOG.info(f"File has already been processed: {local_file_name}. Skipping...")
            return {}

        report_status = CostUsageReportStatus.objects.filter(
            report_name=local_file_name, manifest_id=manifest_id
        ).first()
        if not report_status:
            LOG.info(
                log_json(
                    self.tracing_id,
                    msg="no CostUsageReportStatus found",
                    context=self.context,
                    report_name=local_file_name,
                    manifest_id=manifest_id,
                )
            )
            return {}
        report_status.set_celery_task_id(report_context.get("task_id"))

        try:
            file_name, etag, _, split_files, date_range = self._downloader.download_file(
                report, report_status.etag, manifest_id=manifest_id, start_date=date_time
            )
            report_status.etag = etag
            report_status.save(update_fields=["etag"])
        except (
            AWSReportDownloaderNoFileError,
            AzureReportDownloaderError,
            UploadError,
            CreateDailyArchivesError,
        ) as error:
            ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.FAILED, manifest_id)
            report_status.update_status(CombinedChoices.FAILED)
            LOG.warning(f"Unable to download report file: {report}. Reason: {str(error)}")
            return {}

        # The create_table flag is used by the ParquetReportProcessor
        # to create a Hive/Trino table.
        report = {
            "file": file_name,
            "split_files": split_files,
            "compression": report_context.get("compression"),
            "start_date": date_time,
            "assembly_id": report_context.get("assembly_id"),
            "manifest_id": manifest_id,
            "provider_uuid": self.provider_uuid,
            "create_table": report_context.get("create_table", False),
            "start": date_range.get("start"),
            "end": date_range.get("end"),
            "invoice_month": date_range.get("invoice_month"),
        }
        ReportManifestDBAccessor().update_manifest_state(ManifestStep.DOWNLOAD, ManifestState.END, manifest_id)
        return report
