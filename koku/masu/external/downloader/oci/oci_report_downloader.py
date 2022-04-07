#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Local Report Downloader."""
import datetime
import logging
import os

import oci
from dateutil.relativedelta import relativedelta
from rest_framework.exceptions import ValidationError

from api.common import log_json
from api.utils import DateHelper
from koku.settings import OCI_CONFIG
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from providers.oci.provider import OCIProvider


DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


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
        self.tenant = self.credentials.get("tenant")
        self.reporting_namespace = "bling"
        self._oci_client = self._get_oci_client()
        self.files_list = self._extract_names()

    @staticmethod
    def _get_oci_client():
        # Grab oci config credentials
        config = OCI_CONFIG
        oci_objects_client = oci.object_storage.ObjectStorageClient(config)

        return oci_objects_client

    def _check_access(self):
        try:
            OCIProvider().cost_usage_source_is_reachable(self.credentials, self.data_source)
        except ValidationError as ex:
            msg = f"OCI source ({self._provider_uuid}) for {self.customer_name} is not reachable. Error: {str(ex)}"
            LOG.warning(log_json(self.tracing_id, msg, self.context))
            raise OCIReportDownloaderError(str(ex))

    def _collect_reports(self, prefix, tag=None):
        """
        Collect reports from OCI

        Returns:
            list of reports
        """
        # Tenant bucket
        reporting_bucket = self.tenant

        report_list = self._oci_client.list_objects(
            self.reporting_namespace,
            reporting_bucket,
            prefix=prefix,
            fields="etag,md5,timeCreated,timeModified",
            start_after=tag,
        )
        return report_list

    def _extract_names(self, usage_tag=None, cost_tag=None):
        """
        Get list of file names.

        Returns:
             list of files for download

        """
        # Check we can acees reports
        self._check_access

        reports = []
        usage_reports = self._collect_reports(self, prefix="reports/usage-csv", tag=usage_tag)
        cost_reports = self._collect_reports(self, prefix="reports/cost-csv", tag=cost_tag)
        reports = usage_reports.data.objects + cost_reports.data.objects

        file_names = []
        for report in reports:
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
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_list = manifest_accessor.get_manifest_list_for_provider_and_bill_date(
                self._provider_uuid, start_date
            )
        if not manifest_list:
            # if it is an empty list, that means it is the first time we are
            # downloading this month, so we need to update our
            # scan range to include the full month.
            self.scan_start = start_date
            end_of_month = start_date + relativedelta(months=1)
            if isinstance(end_of_month, datetime.datetime):
                end_of_month = end_of_month.date()
            if end_of_month < self.scan_end:
                self.scan_end = end_of_month
            today = DateAccessor().today().date()
            if today < end_of_month:
                self.scan_end = today
        invoice_month = start_date.strftime("%Y%m")
        assembly_id = ":".join([str(self._provider_uuid), str(invoice_month)])

        dh = DateHelper()
        start_date = dh.invoice_month_start(str(invoice_month))
        bill_date = self.scan_start.replace(day=1)
        file_names = self.files_list

        manifest_data = {
            "assembly_id": assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": bill_date,
            "end_date": self.scan_end,
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
        reporting_bucket = self.tenant
        # The Object Storage namespace used biling reports is bling.
        reporting_namespace = self.reporting_namespace

        directory_path = self._get_local_directory_path()
        full_local_path = self._get_local_file_path(directory_path, key)
        os.makedirs(directory_path, exist_ok=True)
        etag = key

        msg = f"Downloading {key} to {full_local_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        object_details = self._oci_client.get_object(reporting_namespace, reporting_bucket, key)

        with open(full_local_path, "wb") as f:
            for chunk in object_details.data.raw.stream(1024 * 1024, decode_content=False):
                f.write(chunk)

        directory_path = self._get_local_directory_path
        full_file_path = self._get_local_file_path(directory_path, key)

        file_creation_date = None
        msg = f"Returning full_file_path: {full_file_path}"
        LOG.info(log_json(self.request_id, msg, self.context))
        msg = f"Downloading {key} to {full_file_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        report_file = self._oci_client.get_object(reporting_namespace, reporting_bucket, key)

        with open(full_file_path, "wb") as f:
            for chunk in report_file.data.raw.stream(1024 * 1024, decode_content=False):
                f.write(chunk)

            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

        return full_file_path, etag, file_creation_date, []

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

    def _remove_manifest_file(self, manifest_file):
        """Clean up the manifest file after extracting information."""
        try:
            os.remove(manifest_file)
            msg = f"Deleted manifest file at {manifest_file}"
            LOG.info(log_json(self.request_id, msg, self.context))
        except OSError:
            msg = f"Could not delete manifest file at {manifest_file}"
            LOG.info(log_json(self.request_id, msg, self.context))
        return None
