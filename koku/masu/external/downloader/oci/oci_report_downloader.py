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
from masu.util.oci.common import OCI_REPORT_TYPES
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
        data_frame = pd.read_csv(file_path, dtype=pd.StringDtype(storage="pyarrow"))
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {error}")
        raise error

    report_type = "usage" if "usage" in filename else "cost"
    unique_days = pd.to_datetime(data_frame["lineItem/intervalUsageStart"]).dt.date.unique()
    if unique_days.size < 1:
        return monthly_files, {}

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
            context,
        )
        monthly_file_names.append(monthly_file.get("filepath"))
    return monthly_file_names, date_range


class OCIReportDownloaderError(Exception):
    """OCI Report Downloader error."""


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
        self.date_fmt = "%Y%m"

        try:
            OCIProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = f"OCI source ({self._provider_uuid}) for {self.customer_name} is not reachable. Error: {ex}"
            LOG.warning(log_json(self.tracing_id, msg=msg, context=self.context))
            raise OCIReportDownloaderError(str(ex))

    @staticmethod
    def _get_oci_client(region):
        # Grab oci config credentials
        config = OCI_CONFIG
        config["region"] = region
        oci_objects_client = object_storage.ObjectStorageClient(config)

        return oci_objects_client

    def get_report_tracker(self, assembly_id):
        """
        Collect dict of last report previously downloaded

        Returns:
            Dict of file names
        """
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                report_tracker = manifest.report_tracker
            else:
                report_tracker = {"cost": "", "usage": ""}

        return report_tracker

    def update_report_tracker(self, report_type, key, manifest_id):
        """
        Update stored dict of last report previously downloaded

        Returns:
            Dict of file names
        """
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)
            if manifest:
                report_tracker = manifest.report_tracker
                report_tracker[report_type] = key
                manifest.report_tracker = report_tracker
                manifest.save()
                return report_tracker

    def _collect_reports(self, prefix, last_report=None):
        """
        Collect list of report objects from OCI

        Returns:
            list_objects_response
        """

        list_objects_response = self._oci_client.list_objects(
            self.namespace,
            self.bucket,
            prefix=prefix,
            fields="timeCreated",
            start_after=last_report,
        )
        return list_objects_response

    def _prepare_monthly_files_dict(self, start_date, end_date):
        """
        Prepare a dictionary of monthly files

        Args:
            start_date (datetime): start date
            end_date (datetime): end date

        Returns:
            monthly_files_dict: dictionary of monthly files
                Example: monthly_files_dict = {
                            "2022-09-01": [],
                            "2022-10-01": [],
                         }
        """

        monthly_files_dict = {}

        if start_date.strftime(self.date_fmt) == end_date.strftime(self.date_fmt):
            monthly_files_dict.update({start_date.date(): []})
        else:
            date_range_list = list(pd.date_range(start=start_date, end=end_date, freq="MS"))
            for month in date_range_list:
                monthly_files_dict.update({month.date(): []})

        LOG.info(f"Prepared Monthly files dictionary: {monthly_files_dict}")
        return monthly_files_dict

    def _extract_names(self, assembly_id=None):
        """Get list of cost and usage report objects for manifest/downloading."""

        report_tracker = self.get_report_tracker(assembly_id)
        last_report_type_map = {"cost": report_tracker.get("cost", ""), "usage": report_tracker.get("usage", "")}
        report_objects_list = []

        # Collecting CUR's from OCI bucket
        for report_type in OCI_REPORT_TYPES:
            prefix = f"reports/{report_type}-csv"
            report_obj_list = self._collect_reports(prefix=prefix, last_report=last_report_type_map.get(report_type))
            report_objects_list.extend(report_obj_list.data.objects)

        return report_objects_list

    def _get_month_report_names(self, month, report_objects_list):
        """Get month report objects from list of report objects"""

        month_report_obj_list = []
        if month and report_objects_list:
            for report in report_objects_list:
                # grab files created within the ingest month
                if report.time_created.strftime(self.date_fmt) == month.strftime(self.date_fmt):
                    month_report_obj_list.append(report.name)
        return month_report_obj_list

    def get_manifest_context_for_date(self, date):
        """
        Get the manifest context for a provided date.

        Args:
            date (Date): The starting datetime object

        Returns:
            [{}] List of dictionary of monthly reports using the following keys:
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

        # Grabbing ingest delta for initial ingest
        months_delta = Config.INITIAL_INGEST_NUM_MONTHS
        ingest_month = date + relativedelta(months=-months_delta)
        ingest_month = ingest_month.replace(day=1)
        # get monthly report-filenames template
        monthly_report_files = self._prepare_monthly_files_dict(ingest_month, date)
        dh = DateHelper()
        report_manifests_list = []
        extracted_report_obj_list = self._extract_names()

        for month in monthly_report_files.keys():
            monthly_report = {}
            invoice_month = month.strftime(self.date_fmt)
            assembly_id = ":".join([str(self._provider_uuid), invoice_month])
            month_report_names = self._get_month_report_names(month, extracted_report_obj_list)
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in month_report_names
            ]
            if files_list:
                manifest_id = self._process_manifest_db_record(
                    assembly_id, month.strftime("%Y-%m-%d"), len(month_report_names), dh.now
                )
                monthly_report["manifest_id"] = manifest_id
                monthly_report["assembly_id"] = assembly_id
                monthly_report["compression"] = manifest_dict.get("compression")
                monthly_report["files"] = files_list
                report_manifests_list.append(monthly_report)

        LOG.info(f"Report Manifests List: {report_manifests_list}")
        return report_manifests_list

    def _generate_monthly_pseudo_manifest(self, start_date):
        """
        Generate a dict representing an analog to other providers' "manifest" files.

        OCI does not produce a manifest file for monthly periods. So, we check for
        files in the bucket that match dates within the monthly period starting on
        the requested start_date.

        Args:
            start_date (datetime.datetime): when to start gathering reporting data

        Returns:
            Manifest-like dict with keys and value placeholders
                assembly_id - (String): empty string
                compression - (String): Report compression format
                start_date - (Datetime): billing period start date
                file_names - (list): empty list to hold reports' filenames.

        """

        manifest_data = {
            "assembly_id": "",
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "file_names": [],
        }
        LOG.info(f"Manifest Data: {manifest_data}")
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
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            msg = f"Downloading {key} to {full_local_path}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            report_file = self._oci_client.get_object(bucket_namespace, bucket, key)

            with open(full_local_path, "wb") as f:
                for chunk in report_file.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
                file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_local_path))

            if "usage" in key:
                self.update_report_tracker("usage", key, manifest_id)
            else:
                self.update_report_tracker("cost", key, manifest_id)

            file_names, date_range = create_monthly_archives(
                self.tracing_id,
                self.account,
                self._provider_uuid,
                key,
                full_local_path,
                manifest_id,
                self.context,
            )

            if not file_names and not date_range:
                raise OCIReportDownloaderError("Empty report retrieved")

        except Exception as err:
            err_msg = (
                "Could not complete download. "
                f"\n Provider: {self._provider_uuid}"
                f"\n Customer: {self.customer_name}"
                f"\n Response: {err}"
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
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        full_local_path = os.path.join(directory_path, local_file_name)
        return full_local_path
