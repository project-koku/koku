#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Local Report Downloader."""
import logging
import os

from api.common import log_json
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.gcp.gcp_report_downloader import create_daily_archives
from masu.external.downloader.report_downloader_base import ReportDownloaderBase

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class GCPReportDownloaderError(Exception):
    """GCP Report Downloader error."""

    pass


class GCPLocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    GCP Cost and Usage Report Downloader.

    For configuration of GCP, see
    https://cloud.google.com/billing/docs/how-to/export-data-bigquery
    """

    def __init__(self, customer_name, data_source, **kwargs):
        """
        Constructor.

        Args:
            customer_name  (str): Name of the customer
            data_source    (dict): dict containing name of GCP storage bucket

        """
        super().__init__(**kwargs)
        self.data_source = data_source
        self.storage_location = self.data_source.get("local_dir")
        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self._provider_uuid = kwargs.get("provider_uuid")
        self.file_mapping = self._extract_names()

    def _extract_names(self):
        """
        Find the report name and prefix given the bucket path.

        Args:
            bucket (String): Path to the local file

        Returns:
            (String, String) report_prefix, report_name

        """
        if not self.storage_location:
            err_msg = "The required local_dir parameter was not provided in the data_source json."
            raise GCPReportDownloaderError(err_msg)
        file_mapping = {}
        for root, dirs, files in os.walk(self.storage_location, followlinks=True):
            for file in files:
                if file.endswith(".csv"):
                    report_name = os.path.splitext(file)[0]
                    invoice_month, etag, date_range = report_name.split("_")
                    if ":" not in date_range:
                        # if date range does not contain the `:`, it is not a file to process
                        continue
                    scan_start, scan_end = date_range.split(":")
                    file_info = {"start": scan_start, "end": scan_end, "filename": file}
                    if not file_mapping.get(invoice_month):
                        file_mapping[invoice_month] = {}
                    file_mapping[invoice_month][etag] = file_info
        return file_mapping

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

        GCP does not produce a manifest file for monthly periods. So, we check for
        files in the bucket that match dates within the monthly period starting on
        the requested start_date.

        Args:
            start_date (datetime.datetime): when to start gathering reporting data

        Returns:
            Manifest-like dict with list of relevant found files.

        """
        etag = None
        invoice_month = start_date.strftime("%Y%m")
        etags = self.file_mapping.get(str(invoice_month), {})
        for etag_key in etags.keys():
            with ReportManifestDBAccessor() as manifest_accessor:
                assembly_id = ":".join([str(self._provider_uuid), etag_key, str(invoice_month)])
                manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                continue
            etag = etag_key
            break
        if not etag:
            return {}
        dh = DateHelper()
        start_date = dh.gcp_invoice_month_start(str(invoice_month))
        end_date = self.file_mapping[invoice_month][etag]["end"]
        file_names = [self.file_mapping[invoice_month][etag]["filename"]]
        manifest_data = {
            "assembly_id": assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "end_date": end_date,  # inclusive end date
            "file_names": file_names,
        }
        return manifest_data

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with GCP the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of GCP storage blob

        """
        return report

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a file from GCP storage bucket.

        If we have a stored etag and it matches the current GCP blob, we can
        safely skip download since the blob/file content must not have changed.

        Args:
            key (str): name of the blob in the GCP storage bucket
            stored_etag (str): optional etag stored in our DB for comparison

        Returns:
            tuple(str, str) with the local filesystem path to file and GCP's etag.

        """
        report_name = os.path.splitext(key)[0]
        etag = report_name.split("_")[1]
        full_local_path = self._get_local_file_path(key, etag)
        msg = f"Returning full_file_path: {full_local_path}"
        LOG.info(log_json(self.request_id, msg, self.context))
        dh = DateHelper()

        file_names = create_daily_archives(
            self.request_id,
            self.account,
            self._provider_uuid,
            key,
            full_local_path,
            manifest_id,
            start_date,
            self.context,
        )

        return full_local_path, etag, dh.today, file_names

    def _get_local_file_path(self, key, etag):
        """
        Get the local file path destination for a downloaded file.

        Args:
            directory_path (str): base local directory path
            key (str): name of the blob in the GCP storage bucket

        Returns:
            str of the destination local file path.

        """
        if etag not in self.storage_location:
            final_path = f"{self.storage_location}/{etag}"
        else:
            final_path = f"{self.storage_location}"
        local_file_name = key.replace("/", "_")
        msg = f"Local filename: {local_file_name}"
        LOG.info(log_json(self.request_id, msg, self.context))
        full_local_path = os.path.join(final_path, local_file_name)
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
