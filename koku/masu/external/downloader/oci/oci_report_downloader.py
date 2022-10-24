#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Local Report Downloader."""
import datetime
import logging
import os
import uuid

import pandas as pd
from dateutil import parser
from dateutil.relativedelta import relativedelta
from oci import object_storage
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku.settings import OCI_CONFIG
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from providers.oci.provider import OCIProvider

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


def divide_csv_monthly(file_path, filename):
    """
    Split local file into daily content.
    """
    monthly_files = []
    directory = os.path.dirname(file_path)

    try:
        data_frame = pd.read_csv(file_path)
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {str(error)}")
        raise error

    report_type = "usage" if "usage" in filename else "cost"
    unique_days = pd.to_datetime(data_frame["lineItem/intervalUsageStart"]).dt.date.unique()
    days = list({day.strftime("%Y-%m-%d") for day in unique_days})
    date_range = {"start": min(days), "end": max(days)}
    months = list({day.strftime("%Y-%m") for day in unique_days})
    monthly_data_frames = [
        {"data_frame": data_frame[data_frame["lineItem/intervalUsageStart"].str.contains(month)], "date": month}
        for month in months
    ]

    for daily_data in monthly_data_frames:
        month = daily_data.get("date")
        start_date = parser.parse(month + "-01")
        df = daily_data.get("data_frame")
        month_file = f"{report_type}_{uuid.uuid4()}.{month}.csv"
        month_filepath = f"{directory}/{month_file}"
        df.to_csv(month_filepath, index=False, header=True)
        monthly_files.append(
            {"filename": month_file, "filepath": month_filepath, "report_type": report_type, "start_date": start_date}
        )
    return monthly_files, date_range


def create_monthly_archives(tracing_id, account, provider_uuid, filename, filepath, manifest_id, context={}):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        tracing_id (str): The tracing id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filename (str): The OCP file name
        filepath (str): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    monthly_file_names = []

    monthly_files, date_range = divide_csv_monthly(filepath, filename)
    for monthly_file in monthly_files:
        # Push to S3
        s3_csv_path = get_path_prefix(
            account,
            Provider.PROVIDER_OCI,
            provider_uuid,
            monthly_file.get("start_date"),
            Config.CSV_DATA_TYPE,
            report_type=monthly_file.get("report_type"),
        )
        copy_local_report_file_to_s3_bucket(
            tracing_id,
            s3_csv_path,
            monthly_file.get("filepath"),
            monthly_file.get("filename"),
            manifest_id,
            monthly_file.get("start_date"),
            context,
        )
        monthly_file_names.append(monthly_file.get("filepath"))
    return monthly_file_names, date_range


class OCIReportDownloaderError(Exception):
    """OCI Report Downloader error."""

    pass


class OCIReportDownloaderNoFileError(Exception):
    """OCI Report Downloader error for missing file."""


class OCIReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    OCI Cost and Usage Report Downloader.

    For configuration of OCI, see
    https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/accessingusagereports.htm
    """

    def __init__(self, customer_name, data_source, **kwargs):
        """
        Constructor.

        Args:
            customer_name  (str): Name of the customer
            data_source    (dict): dict containing name of OCI storage bucket

        """
        super().__init__(**kwargs)
        self.data_source = data_source
        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self._provider_uuid = kwargs.get("provider_uuid")
        self.namespace = data_source.get("bucket_namespace")
        self.bucket = data_source.get("bucket")
        self.region = data_source.get("bucket_region")
        self._oci_client = self._get_oci_client(self.region)

        try:
            OCIProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = f"OCI source ({self._provider_uuid}) for {self.customer_name} is not reachable. Error: {str(ex)}"
            LOG.warning(log_json(self.tracing_id, msg, self.context))
            raise OCIReportDownloaderError(str(ex))

    @staticmethod
    def _get_oci_client(region):
        # Grab oci config credentials
        config = OCI_CONFIG
        config["region"] = region
        oci_objects_client = object_storage.ObjectStorageClient(config)

        return oci_objects_client

    def get_last_reports(self, assembly_id):
        """
        Collect dict of last report previously downloaded

        Returns:
            Dict of file names
        """
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                last_reports = manifest.last_reports
            else:
                last_reports = {"cost": "", "usage": ""}

        return last_reports

    def update_last_reports(self, report_type, key, manifest_id):
        """
        Update stored dict of last report previously downloaded

        Returns:
            Dict of file names
        """
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            if manifest:
                last_reports = manifest.last_reports
                last_reports[report_type] = key
                manifest.last_reports = last_reports
                manifest.save()
                return last_reports

    def _collect_reports(self, prefix, last_report=None):
        """
        Collect list of reports from OCI

        Returns:
            list of reports
        """
        report_list = self._oci_client.list_objects(
            self.namespace,
            self.bucket,
            prefix=prefix,
            fields="timeCreated",
            start_after=last_report,
        )
        return report_list

    def _prepare_monthly_files(self, start_month, end_month):
        """
        Prepare a dictionary of monthly files

        Returns:
            dictionary of monthly files

            Example:
                monthly_files_dict = {
                    "2022-09-01": [],
                    "2022-10-01": [],
                }
        """
        month_dates = pd.date_range(start=start_month, end=end_month, freq="MS")
        monthly_files_dict = {}
        for month in month_dates:
            monthly_files_dict.update({month.date(): []})
        return monthly_files_dict

    def _extract_names(self, assembly_id, start_date):
        """
        Get list of file names for manifest/downloading.

        Returns:
            list of files for download

        """
        # Grabbing ingest delta for initial ingest
        months_delta = Config.INITIAL_INGEST_NUM_MONTHS
        ingest_month = start_date + relativedelta(months=-months_delta)
        ingest_month = ingest_month.replace(day=1)
        # Pulling a dict of last downloaded files from manifest
        last_reports = self.get_last_reports(assembly_id)
        initial_ingest = True if last_reports == {"cost": "", "usage": ""} else False
        usage_report = last_reports["usage"] if "usage" in last_reports else ""
        cost_report = last_reports["cost"] if "cost" in last_reports else ""
        # Collecting CUR's from OCI bucket
        usage_reports = self._collect_reports(prefix="reports/usage-csv", last_report=usage_report)
        cost_reports = self._collect_reports(prefix="reports/cost-csv", last_report=cost_report)
        reports = usage_reports.data.objects + cost_reports.data.objects
        # create monthly files pseudo dictionary
        monthly_files_dict = self._prepare_monthly_files(ingest_month, start_date)
        # Create list of filenames for downloading
        file_names = []
        for report in reports:
            _report_date = report.time_created.replace(microsecond=0, second=0, minute=0, hour=0, day=1).date()
            if initial_ingest:
                # Reduce initial ingest download footprint by only downloading files within the ingest window
                if report.time_created.date() > ingest_month.date():
                    # split files into monthly files
                    if _report_date in monthly_files_dict.keys():
                        monthly_files_dict[_report_date].append(report.name)
                    else:
                        monthly_files_dict[_report_date] = [report.name]
            else:
                monthly_files_dict.update({_report_date: monthly_files_dict[_report_date].append(report.name)})
        for _report_month, _report_files in monthly_files_dict.items():
            file_names.append({"date": _report_month, "files": _report_files})
        LOG.info(f"monthly reports names: {file_names}")
        return file_names

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

        manifest_dict = self._generate_monthly_pseudo_manifest(date)
        if not manifest_dict:
            return report_dict

        dh = DateHelper()
        report_dict_list = []
        for month_files in manifest_dict["file_names"]:
            assembly_id = ":".join([manifest_dict["assembly_id"], str(month_files["date"])])
            manifest_id = self._process_manifest_db_record(
                assembly_id, month_files["date"], len(month_files["files"]), dh._now
            )
            report_dict["assembly_id"] = assembly_id
            report_dict["manifest_id"] = manifest_id
            report_dict["compression"] = manifest_dict.get("compression")
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in month_files.get("files", [])
            ]
            report_dict["files"] = files_list
            report_dict_list.append(report_dict)
        return report_dict_list

    def _generate_monthly_pseudo_manifest(self, start_date):
        """
        Generate a dict representing an analog to other providers' "manifest" files.

        OCI does not produce a manifest file for monthly periods. So, we check for
        files in the bucket that match dates within the monthly period starting on
        the requested start_date.

        Args:
            start_date (datetime.datetime): when to start gathering reporting data

        Returns:
            Manifest-like dict with list of relevant found files.

        """

        assembly_id_prefix = str(self._provider_uuid)
        bill_date = start_date
        file_names = self._extract_names(assembly_id_prefix, start_date)

        manifest_data = {
            "assembly_id": assembly_id_prefix,
            "compression": UNCOMPRESSED,
            "start_date": bill_date,
            "file_names": file_names,
        }
        LOG.info(f"Manifest Data: {str(manifest_data)}")
        return manifest_data

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with OCI the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of OCI storage blob

        """
        local_file_name = report.replace("/", "_")
        return local_file_name

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a file from OCI storage bucket.

        If we have downloaded anything before the start_date, we can
        safely skip download since the blob/file content must not have changed.

        Args:
            key (str): name of the blob in the OCI storage bucket
            stored_etag (str): optional etag stored in our DB for comparison

        Returns:
            tuple(str, str) with the local filesystem path to file and OCI's etag.

        """
        try:
            bucket = self.bucket
            bucket_namespace = self.namespace
            etag = key

            directory_path = self._get_local_directory_path()
            full_local_path = self._get_local_file_path(directory_path, key)
            os.makedirs(directory_path, exist_ok=True)

            file_creation_date = None
            msg = f"Returning full_file_path: {full_local_path}"
            LOG.info(log_json(self.request_id, msg, self.context))
            msg = f"Downloading {key} to {full_local_path}"
            LOG.info(log_json(self.tracing_id, msg, self.context))
            report_file = self._oci_client.get_object(bucket_namespace, bucket, key)

            with open(full_local_path, "wb") as f:
                for chunk in report_file.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
                file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_local_path))

            if "usage" in key:
                self.update_last_reports("usage", key, manifest_id)
            else:
                self.update_last_reports("cost", key, manifest_id)

            file_names, date_range = create_monthly_archives(
                self.tracing_id,
                self.account,
                self._provider_uuid,
                key,
                full_local_path,
                manifest_id,
                self.context,
            )
        except Exception as err:
            err_msg = (
                "Could not complete download."
                f"\n  Provider: {self._provider_uuid}"
                f"\n  Customer: {self.customer_name}"
                f"\n  Response: {err.message}"
            )
            raise OCIReportDownloaderError(err_msg)

        return full_local_path, etag, file_creation_date, file_names, date_range

    def _get_local_directory_path(self):
        """
        Get the local directory path destination for downloading files.

        Returns:
            str of the destination local directory path.

        """
        safe_customer_name = self.customer_name.replace("/", "_")
        directory_path = os.path.join(DATA_DIR, safe_customer_name, "oci")
        return directory_path

    def _get_local_file_path(self, directory_path, key):
        """
        Get the local file path destination for a downloaded file.

        Args:
            directory_path (str): base local directory path
            key (str): name of csv in the OCI storage bucket

        Returns:
            str of the destination local file path.

        """
        local_file_name = key.replace("/", "_")
        msg = f"Local filename: {local_file_name}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        full_local_path = os.path.join(directory_path, local_file_name)
        return full_local_path
