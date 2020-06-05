#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Azure Report Downloader."""
import datetime
import logging
import os

from django.conf import settings

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.azure import common as utils
from masu.util.common import extract_uuids_from_string
from masu.util.common import month_date_range

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureReportDownloaderError(Exception):
    """Azure Report Downloader error."""


class AzureReportDownloaderNoFileError(Exception):
    """Azure Report Downloader error for missing file."""


class AzureReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """Azure Cost and Usage Report Downloader."""

    def __init__(self, task, customer_name, auth_credential, billing_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            task             (Object) bound celery object
            customer_name    (String) Name of the customer
            auth_credential  (Dict) Dictionary containing Azure authentication details.
            report_name      (String) Name of the Cost Usage Report to download (optional)
            billing_source   (Dict) Dictionary containing Azure Storage blob details.

        """
        super().__init__(task, **kwargs)

        if customer_name[4:] in settings.DEMO_ACCOUNTS:
            demo_account = settings.DEMO_ACCOUNTS.get(customer_name[4:])
            LOG.info(f"Info found for demo account {customer_name[4:]} = {demo_account}.")
            if auth_credential.get("client_id") in demo_account:
                demo_info = demo_account.get(auth_credential.get("client_id"))
                self.customer_name = customer_name.replace(" ", "_")
                self._provider_uuid = kwargs.get("provider_uuid")
                self.container_name = demo_info.get("container_name")
                self.directory = demo_info.get("report_prefix")
                self.export_name = demo_info.get("report_name")
                self._azure_client = self._get_azure_client(auth_credential, billing_source)
                return

        self._provider_uuid = kwargs.get("provider_uuid")
        self.customer_name = customer_name.replace(" ", "_")
        if not kwargs.get("is_local"):
            self._azure_client = self._get_azure_client(auth_credential, billing_source)
            export_reports = self._azure_client.describe_cost_management_exports()
            export_report = export_reports[0] if export_reports else {}

            self.export_name = export_report.get("name")
            self.container_name = export_report.get("container")
            self.directory = export_report.get("directory")

    @staticmethod
    def _get_azure_client(credentials, billing_source):
        subscription_id = credentials.get("subscription_id")
        tenant_id = credentials.get("tenant_id")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        resource_group_name = billing_source.get("resource_group")
        storage_account_name = billing_source.get("storage_account")

        service = AzureService(
            tenant_id, client_id, client_secret, resource_group_name, storage_account_name, subscription_id
        )
        return service

    def _get_exports_data_directory(self):
        """Return the path of the exports temporary data directory."""
        directory_path = f"{DATA_DIR}/{self.customer_name}/azure/{self.container_name}"
        os.makedirs(directory_path, exist_ok=True)
        return directory_path

    def _get_report_path(self, date_time):
        """
        Return path of report files.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (String): "/blob_dir/export_name/YYYYMMDD-YYYYMMDD",
                    example: "/cost/costreport/20190801-20190831"

        """
        report_date_range = month_date_range(date_time)
        return f"{self.directory}/{self.export_name}/{report_date_range}"

    def _get_manifest(self, date_time):
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        report_path = self._get_report_path(date_time)
        manifest = {}
        try:
            blob = self._azure_client.get_latest_cost_export_for_path(report_path, self.container_name)
        except AzureCostReportNotFound as ex:
            LOG.info("Unable to find manifest. Error: %s", str(ex))
            return manifest
        report_name = blob.name

        try:
            manifest["assemblyId"] = extract_uuids_from_string(report_name).pop()
        except IndexError:
            message = f"Unable to extract assemblyID from {report_name}"
            raise AzureReportDownloaderError(message)

        billing_period = {
            "start": (report_path.split("/")[-1]).split("-")[0],
            "end": (report_path.split("/")[-1]).split("-")[1],
        }
        manifest["billingPeriod"] = billing_period
        manifest["reportKeys"] = [report_name]
        manifest["Compression"] = UNCOMPRESSED

        return manifest

    def get_report_context_for_date(self, date_time):
        """
        Get the report context for a provided date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([]): List of report files.

        """
        should_download = True
        manifest_dict = {}
        report_dict = {}
        manifest = self._get_manifest(date_time)

        if manifest != {}:
            manifest_dict = self._prepare_db_manifest_record(manifest)
            should_download = self.check_if_manifest_should_be_downloaded(manifest_dict.get("assembly_id"))

        if not should_download:
            manifest_id = self._get_existing_manifest_db_id(manifest_dict.get("assembly_id"))
            stmt = (
                f"This manifest has already been downloaded and processed:\n"
                f" schema_name: {self.customer_name},\n"
                f" provider_uuid: {self._provider_uuid},\n"
                f" manifest_id: {manifest_id}"
            )
            LOG.info(stmt)
            return report_dict

        if manifest_dict:
            manifest_id = self._process_manifest_db_record(
                manifest_dict.get("assembly_id"), manifest_dict.get("billing_start"), manifest_dict.get("num_of_files")
            )

            report_dict["manifest_id"] = manifest_id
            report_dict["assembly_id"] = manifest.get("assemblyId")
            report_dict["compression"] = manifest.get("Compression")
            report_dict["files"] = manifest.get("reportKeys")
        return report_dict

    @property
    def manifest_date_format(self):
        """Set the Azure manifest date format."""
        return "%Y%m%d"

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("assemblyId")
        billing_str = manifest.get("billingPeriod", {}).get("start")
        billing_start = datetime.datetime.strptime(billing_str, self.manifest_date_format)
        num_of_files = len(manifest.get("reportKeys", []))
        return {"assembly_id": assembly_id, "billing_start": billing_start, "num_of_files": num_of_files}

    @staticmethod
    def get_local_file_for_report(report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def download_file(self, key, stored_etag=None):
        """
        Download a file from Azure bucket.

        Args:
            key (str): The object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        local_filename = utils.get_local_file_name(key)
        full_file_path = f"{self._get_exports_data_directory()}/{local_filename}"

        try:
            blob = self._azure_client.get_cost_export_for_key(key, self.container_name)
            etag = blob.etag
        except AzureCostReportNotFound as ex:
            log_msg = f"Error when downloading Azure report for key: {key}. Error {ex}"
            LOG.error(log_msg)
            raise AzureReportDownloaderError(log_msg)

        if etag != stored_etag:
            LOG.info("Downloading %s to %s", key, full_file_path)
            blob = self._azure_client.download_cost_export(key, self.container_name, destination=full_file_path)
        LOG.info("Returning full_file_path: %s, etag: %s", full_file_path, etag)
        return full_file_path, etag
