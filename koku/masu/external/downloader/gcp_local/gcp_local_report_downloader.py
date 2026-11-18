#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Local Report Downloader."""
import datetime
import logging
import os

import pandas as pd

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class GCPReportDownloaderError(Exception):
    """GCP Report Downloader error."""

    pass


def create_daily_archives(tracing_id, account, provider_uuid, filename, filepath, manifest_id, start_date, context):
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
    daily_file_names = []
    date_range = {}
    dh = DateHelper()
    directory = os.path.dirname(filepath)
    try:
        data_frame = pd.read_csv(filepath)
    except Exception as error:
        LOG.error(f"File {filepath} could not be parsed. Reason: {str(error)}")
        raise GCPReportDownloaderError(error)
    # putting it in for loop handles crossover data, when we have distinct invoice_month
    unique_usage_days = pd.to_datetime(data_frame["usage_start_time"]).dt.date.unique()
    days = list({day.strftime("%Y-%m-%d") for day in unique_usage_days})
    date_range = {"start": min(days), "end": max(days)}
    for invoice_month in data_frame["invoice.month"].unique():
        invoice_filter = data_frame["invoice.month"] == invoice_month
        invoice_month_data = data_frame[invoice_filter]
        partition_dates = invoice_month_data.partition_date.unique()
        for partition_date in partition_dates:
            partition_date_filter = invoice_month_data["partition_date"] == partition_date
            invoice_partition_data = invoice_month_data[partition_date_filter]
            start_of_invoice = dh.invoice_month_start(invoice_month)
            s3_csv_path = get_path_prefix(
                account, Provider.PROVIDER_GCP, provider_uuid, start_of_invoice, Config.CSV_DATA_TYPE
            )
            day_file = f"{invoice_month}_{partition_date}.csv"
            day_filepath = f"{directory}/{day_file}"
            invoice_partition_data.to_csv(day_filepath, index=False, header=True)
            copy_local_report_file_to_s3_bucket(tracing_id, s3_csv_path, day_filepath, day_file, manifest_id, context)
            daily_file_names.append(day_filepath)
    return daily_file_names, date_range


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
                report_name = os.path.splitext(file)[0]
                if file.endswith(".csv") and ":" in report_name:
                    invoice_month, etag, date_range = report_name.split("_")
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
        dh = DateHelper()
        manifest_list = self.collect_new_manifests()
        reports_list = []
        for manifest in manifest_list:
            manifest_id = self._process_manifest_db_record(
                manifest["assembly_id"], manifest["bill_date"], len(manifest["files"]), dh.now
            )
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)} for key in manifest.get("files")
            ]
            report_dict = {
                "manifest_id": manifest_id,
                "assembly_id": manifest["assembly_id"],
                "compression": UNCOMPRESSED,
                "files": files_list,
            }
            reports_list.append(report_dict)
        return reports_list

    def collect_new_manifests(self):
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
        manifest_list = []
        for invoice_month in self.file_mapping.keys():
            etags = self.file_mapping.get(str(invoice_month), {})
            for etag_key in etags.keys():
                etag_data = etags.get(etag_key, {})
                bill_date = datetime.datetime.strptime(etag_data["start"], "%Y-%m-%d").replace(day=1)
                with ReportManifestDBAccessor() as manifest_accessor:
                    assembly_id = "|".join([str(etag_data["start"]), str(etag_data["end"]), str(self._provider_uuid)])
                    manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
                if manifest:
                    continue
                etag = etag_key
                break
            if not etag:
                continue
            file_names = [self.file_mapping[invoice_month][etag]["filename"]]
            manifest_data = {
                "assembly_id": assembly_id,
                "bill_date": bill_date,
                "compression": UNCOMPRESSED,
                "files": file_names,
            }
            manifest_list.append(manifest_data)
        return manifest_list

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
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        dh = DateHelper()

        file_names, date_range = create_daily_archives(
            self.request_id,
            self.account,
            self._provider_uuid,
            key,
            full_local_path,
            manifest_id,
            start_date,
            self.context,
        )

        return full_local_path, etag, dh.today, file_names, date_range

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
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        full_local_path = os.path.join(final_path, local_file_name)
        return full_local_path

    def _remove_manifest_file(self, manifest_file):
        """Clean up the manifest file after extracting information."""
        try:
            os.remove(manifest_file)
            msg = f"Deleted manifest file at {manifest_file}"
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        except OSError:
            msg = f"Could not delete manifest file at {manifest_file}"
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        return None
