#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Report Downloader."""
import datetime
import json
import logging
import os

from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.azure import common as utils
from masu.util.common import extract_uuids_from_string
from masu.util.common import get_path_prefix
from masu.util.common import month_date_range

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureReportDownloaderError(Exception):
    """Azure Report Downloader error."""


class AzureReportDownloaderNoFileError(Exception):
    """Azure Report Downloader error for missing file."""


class AzureReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """Azure Cost and Usage Report Downloader."""

    def __init__(self, customer_name, credentials, data_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            credentials      (Dict) Dictionary containing Azure credentials details.
            report_name      (String) Name of the Cost Usage Report to download (optional)
            data_source      (Dict) Dictionary containing Azure Storage blob details.

        """
        super().__init__(**kwargs)

        # Existing schema will start with acct and we strip that prefix for use later
        # new customers include the org prefix in case an org-id and an account number might overlap
        if customer_name.startswith("acct"):
            demo_check = customer_name[4:]
        else:
            demo_check = customer_name
        if demo_check in settings.DEMO_ACCOUNTS:
            demo_account = settings.DEMO_ACCOUNTS.get(demo_check)
            LOG.info(f"Info found for demo account {demo_check} = {demo_account}.")
            if credentials.get("client_id") in demo_account:
                demo_info = demo_account.get(credentials.get("client_id"))
                self.customer_name = customer_name.replace(" ", "_")
                self._provider_uuid = kwargs.get("provider_uuid")
                self.container_name = demo_info.get("container_name")
                self.directory = demo_info.get("report_prefix")
                self.export_name = demo_info.get("report_name")
                self._azure_client = self._get_azure_client(credentials, data_source)
                return

        self._provider_uuid = kwargs.get("provider_uuid")
        self.customer_name = customer_name.replace(" ", "_")
        if not kwargs.get("is_local"):
            self._azure_client = self._get_azure_client(credentials, data_source)
            export_reports = self._azure_client.describe_cost_management_exports()
            export_report = export_reports[0] if export_reports else {}

            self.export_name = export_report.get("name")
            self.container_name = export_report.get("container")
            self.directory = export_report.get("directory")

    @staticmethod
    def _get_azure_client(credentials, data_source):
        subscription_id = credentials.get("subscription_id")
        tenant_id = credentials.get("tenant_id")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        resource_group_name = data_source.get("resource_group")
        storage_account_name = data_source.get("storage_account")
        scope = data_source.get("scope")
        export_name = data_source.get("export_name")

        service = AzureService(
            tenant_id,
            client_id,
            client_secret,
            resource_group_name,
            storage_account_name,
            subscription_id,
            scope=scope,
            export_name=export_name,
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
            msg = f"Unable to find manifest. Error: {str(ex)}"
            LOG.info(log_json(self.tracing_id, msg, self.context))
            return manifest, None

        report_name = blob.name
        manifest["reportKeys"] = [report_name]

        # This is either a single CSV file or a JSON manifest containing the
        # CSV file(s) to process.
        if report_name.lower().endswith(".json"):
            # Download the JSON file
            try:
                result = self.download_file(manifest)
            except AzureReportDownloaderError as err:
                msg = f"Unable to get report manifest. Reason: {str(err)}"
                LOG.info(log_json(self.tracing_id, msg, self.context))
                return "", self.empty_manifest, None

            # Extract data from the JSON file
            try:
                with open(result[0]) as f:
                    manifest_json = json.load(f)
            except json.JSONDecodeError as err:
                msg = f"Unable to open JSON manifest. Reason: {err}"
                LOG.info(log_json(self.tracing_id, msg, self.context))

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
        manifest["Compression"] = UNCOMPRESSED

        return manifest, blob.last_modified

    def get_manifest_context_for_date(self, date):
        """
        Get the manifest context for a provided date.

        Args:
            date (Date): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([{"key": full_file_path "local_file": "local file name"}]): List of report files.

        """
        manifest_dict = {}
        report_dict = {}
        manifest, manifest_timestamp = self._get_manifest(date)
        if manifest == {}:
            return report_dict

        manifest_dict = self._prepare_db_manifest_record(manifest)

        if manifest_dict:
            manifest_id = self._process_manifest_db_record(
                manifest_dict.get("assembly_id"),
                manifest_dict.get("billing_start"),
                manifest_dict.get("num_of_files"),
                manifest_timestamp,
            )

            report_dict["manifest_id"] = manifest_id
            report_dict["assembly_id"] = manifest.get("assemblyId")
            report_dict["compression"] = manifest.get("Compression")
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in manifest.get("reportKeys")
            ]
            report_dict["files"] = files_list

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

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a file from Azure bucket.

        Args:
            key (str): The object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        local_filename = utils.get_local_file_name(key)
        full_file_path = f"{self._get_exports_data_directory()}/{local_filename}"

        file_creation_date = None
        try:
            blob = self._azure_client.get_cost_export_for_key(key, self.container_name)
            etag = blob.etag
            file_creation_date = blob.last_modified
        except AzureCostReportNotFound as ex:
            msg = f"Error when downloading Azure report for key: {key}. Error {ex}"
            LOG.error(log_json(self.tracing_id, msg, self.context))
            raise AzureReportDownloaderError(msg)

        msg = f"Downloading {key} to {full_file_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        blob = self._azure_client.download_cost_export(key, self.container_name, destination=full_file_path)
        # Push to S3
        s3_csv_path = get_path_prefix(
            self.account, Provider.PROVIDER_AZURE, self._provider_uuid, start_date, Config.CSV_DATA_TYPE
        )
        copy_local_report_file_to_s3_bucket(
            self.tracing_id, s3_csv_path, full_file_path, local_filename, manifest_id, start_date, self.context
        )

        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)

        if not manifest_accessor.get_s3_csv_cleared(manifest):
            remove_files_not_in_set_from_s3_bucket(self.tracing_id, s3_csv_path, manifest_id)
            manifest_accessor.mark_s3_csv_cleared(manifest)

        msg = f"Returning full_file_path: {full_file_path}, etag: {etag}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        return full_file_path, etag, file_creation_date, [], {}
