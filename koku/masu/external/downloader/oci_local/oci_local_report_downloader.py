#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Local Report Downloader."""
import datetime
import logging
import os
import shutil

import pandas as pd
from dateutil.relativedelta import relativedelta

from api.common import log_json
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.oci.oci_report_downloader import create_monthly_archives
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

    def __init__(self, schema_name, data_source, **kwargs):
        """
        Constructor.

        Args:
            schema_name  (str): Name of the customer
            data_source    (dict): dict containing name of OCI storage bucket

        """
        super().__init__(**kwargs)
        self.data_source = data_source
        self.storage_location = self.data_source.get("bucket")
        self.schema_name = schema_name.replace(" ", "_")
        self.credentials = kwargs.get("credentials", {})
        self._provider_uuid = kwargs.get("provider_uuid", "")

    def _extract_names(self, ingest_month):
        """
        Get list of file names.

        Args:
            ingest_month (datetime): - the month whose files to retrieve

        Returns:
            file_names (list): list of files for the ingest_month

        Note:
            - leveraging OCI nise filenames format, which includes the year and month created
              i.e. [report_usage-0001_2022-09.csv, report_cost-0001_2022-09.csv]
              to appropriately ingest files created in a month
        """

        if not self.storage_location:
            err_msg = "The required bucket parameter was not provided in the data_source json."
            raise OCIReportDownloaderError(err_msg)
        files_list = []
        invoice_month = ingest_month.strftime("%Y-%m")
        file_suffix = f"{invoice_month}.csv"
        for root, dirs, files in os.walk(self.storage_location, followlinks=True):
            for file in files:
                if file.endswith(file_suffix):
                    files_list.append(file)
        return files_list

    def _prepare_monthly_files(self, start_date, end_date):
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
        date_range_list = list(pd.date_range(start=start_date, end=end_date, freq="MS"))
        for month in date_range_list:
            monthly_files_dict.update({month.date(): []})
        LOG.info(f"Prepared Monthly files dictionary: {monthly_files_dict}")
        return monthly_files_dict

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
        # Grabbing ingest delta for initial ingest
        months_delta = Config.INITIAL_INGEST_NUM_MONTHS
        ingest_month = date + relativedelta(months=-months_delta)
        ingest_month = ingest_month.replace(day=1)
        # get monthly report-filenames template
        monthly_report_files = self._prepare_monthly_files(ingest_month, date)

        report_manifests_list = []
        for month in monthly_report_files.keys():
            monthly_report = {}
            invoice_month = month.strftime("%Y-%m")
            assembly_id = ":".join([str(self._provider_uuid), str(invoice_month)])
            month_file_names = self._extract_names(month)
            files_list = [{"key": key, "local_file": self.get_local_file_for_report(key)} for key in month_file_names]
            if files_list:
                manifest_id = self._process_manifest_db_record(assembly_id, str(month), len(month_file_names), dh._now)
                monthly_report["manifest_id"] = manifest_id
                monthly_report["assembly_id"] = assembly_id
                monthly_report["compression"] = manifest_dict.get("compression", "")
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
            Manifest-like dict with list of relevant found files.

        """

        manifest_data = {
            "assembly_id": "",
            "compression": UNCOMPRESSED,
            "start_date": start_date,
            "file_names": [],
        }
        return manifest_data

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.

        Since with OCI the "report" *is* the file name, we simply return it.

        Args:
            report (str): name of OCI storage blob

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
        directory_path = f"{DATA_DIR}/{self.schema_name}/oci-local{self.storage_location}"
        full_file_path = f"{directory_path}/{key}"
        etag = key
        base_path = f"{self.storage_location}/{key}"

        if not os.path.isfile(base_path):
            log_msg = f"Unable to locate {key} in {self.storage_location}"
            raise OCIReportDownloaderNoFileError(log_msg)

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)

        file_creation_date = None
        msg = f"Returning full_file_path: {full_file_path}"
        LOG.info(log_json(self.request_id, msg, self.context))
        if not os.path.isfile(full_file_path):
            msg = f"Downloading {base_path} to {full_file_path}"
            LOG.info(log_json(self.tracing_id, msg, self.context))
            shutil.copy2(base_path, full_file_path)
            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

        file_names, date_range = create_monthly_archives(
            self.tracing_id,
            self.s3_schema_name,
            self._provider_uuid,
            key,
            full_file_path,
            manifest_id,
            self.context,
        )

        return full_file_path, etag, file_creation_date, file_names, date_range

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
