#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Report Downloader."""
import datetime
import json
import logging
import os
import uuid

import pandas as pd
from django.conf import settings

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.azure.azure_service import AzureService
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.azure import common as utils
from masu.util.azure.common import AzureBlobExtension
from masu.util.common import check_setup_complete
from masu.util.common import extract_uuids_from_string
from masu.util.common import get_manifest
from masu.util.common import get_path_prefix
from masu.util.common import month_date_range

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureReportDownloaderError(Exception):
    """Azure Report Downloader error."""


class AzureReportDownloaderNoFileError(Exception):
    """Azure Report Downloader error for missing file."""


def create_daily_archives(
    tracing_id,
    account,
    provider_uuid,
    local_file,
    manifest_id,
    start_date,
    context={},
):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        tracing_id (str): The tracing id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filepath (str): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    daily_file_names = []
    date_range = {}
    file_name = os.path.basename(local_file).split("/")[-1]
    dh = DateHelper()
    manifest = get_manifest(manifest_id)
    directory = os.path.dirname(local_file)
    data_frame = pd.read_csv(local_file)
    days = []
    time_interval = "UsageDateTime"
    if hasattr(data_frame, "Date"):
        time_interval = "Date"
    # Ideally this if below would look at the invoice month column! But as far as I can tell Azure DONT update this!
    if start_date.month < dh.today.month and dh.today.day > 5 or not check_setup_complete(provider_uuid):
        start_delta = start_date
    else:
        if start_date.year == dh.today.year and start_date.month == dh.today.month:
            start_delta = dh.today - datetime.timedelta(days=5) if dh.today.date().day > 5 else dh.today.replace(day=1)
        else:
            start_delta = dh.month_end(start_date) - datetime.timedelta(days=3)
        start_delta = start_delta.replace(tzinfo=None)
    intervals = data_frame[time_interval].unique()
    for interval in intervals:
        if datetime.datetime.strptime(interval, "%m/%d/%Y") >= start_delta:
            if interval not in days:
                days.append(interval)
    if days:
        date_range = {"start": min(days), "end": max(days), "invoice_month": None}
        for day in days:
            daily_data = data_frame[data_frame[time_interval].str.match(day)]
            s3_csv_path = get_path_prefix(
                account, Provider.PROVIDER_AZURE, provider_uuid, start_date, Config.CSV_DATA_TYPE
            )
            day = f"{day.split('/')[2]}-{day.split('/')[0]}-{day.split('/')[1]}"
            day_file = f"{day}_{file_name}"
            if not manifest.report_tracker.get(day):
                manifest.report_tracker[day] = 0
            counter = manifest.report_tracker[day]
            day_file = f"{day}_{counter}.csv"
            manifest.report_tracker[day] = counter + 1
            manifest.save()
            day_filepath = f"{directory}/{day_file}"
            daily_data.to_csv(day_filepath, index=False, header=True)
            copy_local_report_file_to_s3_bucket(
                tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, start_date, context
            )
            daily_file_names.append(day_filepath)
    return daily_file_names, date_range


class AzureReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """Azure Cost and Usage Report Downloader."""

    def __init__(self, customer_name, credentials, data_source, report_name=None, ingress_reports=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            credentials      (Dict) Dictionary containing Azure credentials details.
            report_name      (String) Name of the Cost Usage Report to download (optional)
            data_source      (Dict) Dictionary containing Azure Storage blob details.
            ingress_reports  (List) List of reports from ingress post endpoint (optional)
        """
        super().__init__(**kwargs)
        self.storage_only = data_source.get("storage_only")
        self.ingress_reports = ingress_reports

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
        if not kwargs.get("is_local") and not self.storage_only:
            self._azure_client = self._get_azure_client(credentials, data_source)
            export_reports = self._azure_client.describe_cost_management_exports()
            export_report = export_reports[0] if export_reports else {}

            self.export_name = export_report.get("name")
            self.container_name = export_report.get("container")
            self.directory = export_report.get("directory")

        if self.ingress_reports:
            container = self.ingress_reports[0].split("/")[0]
            self.container_name = container
            self._azure_client = self._get_azure_client(credentials, data_source)

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

    def _get_manifest(self, date_time):  # noqa: C901
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        manifest = {}
        if self.ingress_reports:
            report = self.ingress_reports[0].split(f"{self.container_name}/")[1]
            year = date_time.strftime("%Y")
            month = date_time.strftime("%m")
            dh = DateHelper()
            billing_period = {
                "start": f"{year}{month}01",
                "end": f"{year}{month}{dh.days_in_month(date_time, int(year), int(month))}",
            }
            try:
                blob = self._azure_client.get_file_for_key(report, self.container_name)
            except AzureCostReportNotFound as ex:
                msg = f"Unable to find report. Error: {ex}"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                return manifest, None
            report_name = blob.name
            last_modified = blob.last_modified
            manifest["reportKeys"] = [blob.name]
            manifest["assemblyId"] = uuid.uuid4()
        else:
            report_path = self._get_report_path(date_time)
            billing_period = {
                "start": (report_path.split("/")[-1]).split("-")[0],
                "end": (report_path.split("/")[-1]).split("-")[1],
            }
            try:
                json_manifest = self._azure_client.get_latest_manifest_for_path(report_path, self.container_name)
            except AzureCostReportNotFound as ex:
                json_manifest = None
                msg = f"No JSON manifest exists. {ex}"
                LOG.debug(msg)
            if json_manifest:
                report_name = json_manifest.name
                last_modified = json_manifest.last_modified
                LOG.info(log_json(self.tracing_id, msg=f"Found JSON manifest {report_name}", context=self.context))
                # Download the manifest and extract the list of files.
                try:
                    manifest_tmp = self._azure_client.download_file(
                        report_name, self.container_name, suffix=AzureBlobExtension.json.value
                    )
                except AzureReportDownloaderError as err:
                    msg = f"Unable to get report manifest for {self._provider_uuid}. Reason: {str(err)}"
                    LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                    return {}, None
                # Extract data from the JSON file
                try:
                    with open(manifest_tmp) as f:
                        manifest_json = json.load(f)
                except json.JSONDecodeError as err:
                    msg = f"Unable to open JSON manifest. Reason: {err}"
                    raise AzureReportDownloaderError(msg)
                finally:
                    self._remove_manifest_file(manifest_tmp)
                manifest["reportKeys"] = [blob["blobName"] for blob in manifest_json["blobs"]]
            else:
                try:
                    blob = self._azure_client.get_latest_cost_export_for_path(report_path, self.container_name)
                except AzureCostReportNotFound as ex:
                    msg = f"Unable to find manifest. Error: {ex}"
                    LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                    return manifest, None
                report_name = blob.name
                last_modified = blob.last_modified
                LOG.info(log_json(self.tracing_id, msg=f"Found cost export {report_name}", context=self.context))
                manifest["reportKeys"] = [report_name]

            try:
                manifest["assemblyId"] = extract_uuids_from_string(report_name).pop()
            except IndexError:
                message = f"Unable to extract assemblyID from {report_name}"
                raise AzureReportDownloaderError(message)

        manifest["billingPeriod"] = billing_period
        manifest["Compression"] = UNCOMPRESSED

        return manifest, last_modified

    def _remove_manifest_file(self, manifest_file: str) -> None:
        """Remove the temporary manifest file"""
        try:
            os.unlink(manifest_file)
            msg = f"Deleted manifest file '{manifest_file}'"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        except OSError:
            msg = f"Could not delete manifest file '{manifest_file}'"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

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
        if self.storage_only and not self.ingress_reports:
            LOG.info("Skipping ingest as source is storage_only and requires ingress reports")
            return report_dict
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
        file_names = []
        date_range = {}
        file_creation_date = None
        etag = None
        if not self.ingress_reports:
            try:
                blob = self._azure_client.get_file_for_key(key, self.container_name)
                etag = blob.etag
                file_creation_date = blob.last_modified
            except AzureCostReportNotFound as ex:
                msg = f"Error when downloading Azure report for key: {key}. Error {ex}"
                LOG.error(log_json(self.tracing_id, msg=msg, context=self.context))
                raise AzureReportDownloaderError(msg)

        local_filename = utils.get_local_file_name(key)
        full_file_path = f"{self._get_exports_data_directory()}/{local_filename}"
        msg = f"Downloading {key} to {full_file_path}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        self._azure_client.download_file(
            key, self.container_name, destination=full_file_path, ingress_reports=self.ingress_reports
        )

        file_names, date_range = create_daily_archives(
            self.tracing_id,
            self.account,
            self._provider_uuid,
            full_file_path,
            manifest_id,
            start_date,
            self.context,
        )

        msg = f"Download complete for {key}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        return full_file_path, etag, file_creation_date, file_names, date_range
