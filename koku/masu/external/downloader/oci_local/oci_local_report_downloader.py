#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Local Report Downloader."""
import datetime
import hashlib
import logging
import os
import shutil

from api.common import log_json
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase


DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class OCIReportDownloaderError(Exception):
    """OCI Report Downloader error."""

    pass


class OCIReportDownloaderNoFileError(Exception):
    """OCI Report Downloader error for missing file."""


class OCILocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
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
        self.storage_location = self.data_source.get("local_dir")
        self.customer_name = customer_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self._provider_uuid = kwargs.get("provider_uuid")
        self.files_list = self._extract_names()

    def _extract_names(self):
        """
        Get list of file names.

        Returns:
            () bucket location

        """
        if not self.storage_location:
            err_msg = "The required local_dir parameter was not provided in the data_source json."
            raise OCIReportDownloaderError(err_msg)
        files_list = []
        for root, dirs, files in os.walk(self.storage_location, followlinks=True):
            for file in files:
                if file.endswith(".csv"):
                    files_list.append(file)
        return files_list

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
        file_names = self.files_list
        manifest_data = {
            "assembly_id": assembly_id,
            "compression": UNCOMPRESSED,
            "start_date": start_date,
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
        Download a file from OCI storage bucket.

        If we have a stored etag and it matches the current OCI blob, we can
        safely skip download since the blob/file content must not have changed.

        Args:
            key (str): name of the blob in the OCI storage bucket
            stored_etag (str): optional etag stored in our DB for comparison

        Returns:
            tuple(str, str) with the local filesystem path to file and OCI's etag.

        """
        tenancy = self.credentials.get("tenant")

        directory_path = f"{DATA_DIR}/{self.customer_name}/oci-local/{tenancy}"
        full_file_path = f"{directory_path}/{key}"

        base_path = f"/tmp/oci_local/{key}"

        if not os.path.isfile(base_path):
            log_msg = f"Unable to locate {base_path} in {tenancy}"
            raise OCIReportDownloaderNoFileError(log_msg)

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        etag_hasher = hashlib.new("ripemd160")
        etag_hasher.update(bytes(key, "utf-8"))
        etag = etag_hasher.hexdigest()

        file_creation_date = None
        msg = f"Returning full_file_path: {full_file_path}"
        LOG.info(log_json(self.request_id, msg, self.context))
        if etag != stored_etag or not os.path.isfile(full_file_path):
            msg = f"Downloading {base_path} to {full_file_path}"
            LOG.info(log_json(self.tracing_id, msg, self.context))
            shutil.copy2(base_path, full_file_path)
            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

        return full_file_path, etag, file_creation_date, []

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
