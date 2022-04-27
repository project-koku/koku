#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Local Report Downloader."""
import datetime
import logging
import os
from uuid import uuid4

import oci
import pandas as pd
from dateutil import parser
from dateutil.relativedelta import relativedelta
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
    months = list({day.strftime("%Y-%m") for day in unique_days})
    monthly_data_frames = [
        {"data_frame": data_frame[data_frame["lineItem/intervalUsageStart"].str.contains(month)], "date": month}
        for month in months
    ]

    for daily_data in monthly_data_frames:
        month = daily_data.get("date")
        start_date = parser.parse(month + "-01")
        df = daily_data.get("data_frame")
        month_file = f"{report_type}_{uuid4()}.{month}.csv"
        month_filepath = f"{directory}/{month_file}"
        df.to_csv(month_filepath, index=False, header=True)
        monthly_files.append(
            {"filename": month_file, "filepath": month_filepath, "report_type": report_type, "start_date": start_date}
        )
    return monthly_files


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

    monthly_files = divide_csv_monthly(filepath, filename)
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
    return monthly_file_names


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
        oci_objects_client = oci.object_storage.ObjectStorageClient(config)

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
        initial_ingest = True if last_reports == {} else False
        usage_report = last_reports["usage"] if "usage" in last_reports else ""
        cost_report = last_reports["cost"] if "cost" in last_reports else ""
        # Collecting CUR's from OCI bucket
        usage_reports = self._collect_reports(prefix="reports/usage-csv", last_report=usage_report)
        cost_reports = self._collect_reports(prefix="reports/cost-csv", last_report=cost_report)
        reports = usage_reports.data.objects + cost_reports.data.objects
        # Create list of filenames for downloading
        file_names = []
        for report in reports:
            if initial_ingest:
                # Reduce initial ingest download footprint by only downloading files within the ingest window
                if report.time_created.date() > ingest_month:
                    file_names.append(report.name)
            else:
                file_names.append(report.name)
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

        file_names_count = len(manifest_dict["file_names"])
        dh = DateHelper()
        manifest_id = self._process_manifest_db_record(
            manifest_dict["assembly_id"], manifest_dict["start_date"], file_names_count, dh._now
        )

        report_dict["manifest_id"] = manifest_id
        report_dict["assembly_id"] = manifest_dict.get("assembly_id")
        report_dict["compression"] = manifest_dict.get("compression")
        files_list = [
            {"key": key, "local_file": self.get_local_file_for_report(key)}
            for key in manifest_dict.get("file_names", [])
        ]
        report_dict["files"] = files_list
        return report_dict

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
        invoice_month = start_date.strftime("%Y%m")
        assembly_id = ":".join([str(self._provider_uuid), str(invoice_month)])

        dh = DateHelper()
        start_date = dh.invoice_month_start(str(invoice_month))
        bill_date = start_date
        file_names = self._extract_names(assembly_id, start_date)

        manifest_data = {
            "assembly_id": assembly_id,
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

        file_names = create_monthly_archives(
            self.tracing_id,
            self.account,
            self._provider_uuid,
            key,
            full_local_path,
            manifest_id,
            self.context,
        )

        return full_local_path, etag, file_creation_date, file_names

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
