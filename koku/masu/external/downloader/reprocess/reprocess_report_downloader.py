#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Reprocess CSV Report Downloader."""
import datetime
import logging
import os
import uuid
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings

from api.common import log_json
from api.utils import DateHelper
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util import common as com_utils
from masu.util.aws import common as utils

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class ReportDownloaderError(Exception):
    """Report Downloader error."""


class ReportDownloaderNoFileError(Exception):
    """Report Downloader error for missing file."""


class ReprocessReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    Reprocess Report Downloader for reprocessing CSV files to parquet.

    """

    def __init__(self, customer_name, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer

        """
        super().__init__(**kwargs)

        self.customer_name = customer_name.replace(" ", "_")
        self._provider_uuid = kwargs.get("provider_uuid")
        self._provider_type = kwargs.get("provider_type")
        self._tracing_id = kwargs.get("tracing_id")

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
        if manifest_dict:
            assembly_id = manifest_dict.get("assembly_id")
            manifest_id = self._process_manifest_db_record(
                assembly_id,
                date.strftime("%Y-%m-%d"),
                len(manifest_dict.get("file_names")),
                date,
            )
            report_dict["assembly_id"] = assembly_id
            report_dict["compression"] = manifest_dict.get("compression")
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)}
                for key in manifest_dict.get("file_names")
            ]

        report_dict["manifest_id"] = manifest_id
        report_dict["files"] = files_list
        return report_dict

    def _generate_monthly_pseudo_manifest(self, date):
        """
        Generate a dict representing an analog to other providers "manifest" files.

        Args:
            date: Date for processed files

        Returns:
            Manifest-like dict with keys and value placeholders
                assembly_id - (String): empty string
                compression - (String): Report compression format
                start_date - (Datetime): billing period start date
                file_names - (list): list of filenames.
        """
        manifest_data = {
            "assembly_id": uuid.uuid4(),
            "compression": UNCOMPRESSED,
            "start_date": date,
            "file_names": self._build_csv_file_list(date),
        }
        LOG.info(f"Manifest Data: {str(manifest_data)}")
        return manifest_data

    def _build_csv_file_list(self, start_date):
        """
        List all csv files for provider and processing month

        Args:
            date: Used to collect csv files for date month

        Returns:
            List of keys from s3 objects for provider month path
        """
        csv_path_prefix = com_utils.get_path_prefix(
            self.account, self._provider_type, self._provider_uuid, start_date, Config.CSV_DATA_TYPE
        )
        reports_to_download = []
        get_objects = utils._get_s3_objects(csv_path_prefix)
        for obj_summary in get_objects:
            reports_to_download.append(obj_summary.Object().key)

        return reports_to_download

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("assemblyId")
        billing_str = manifest.get("billingPeriod", {}).get("start")
        billing_start = datetime.datetime.strptime(billing_str, self.manifest_date_format)
        num_of_files = len(manifest.get("reportKeys", []))
        return {"assembly_id": assembly_id, "billing_start": billing_start, "num_of_files": num_of_files}

    def get_local_file_for_report(self, report):
        """
        Get the name of the file for the report.
        Args:
            report (str): s3 filename
        """
        report = report.split("/")[-1]
        return report

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """Download an S3 object to file."""
        dh = DateHelper()
        s3_etag = None
        file_names = []
        date_range = {
            "start": dh.month_start(start_date),
            "end": dh.month_end(start_date),
            "invoice_month": dh.invoice_month_from_bill_date(start_date),
        }
        bucket = settings.S3_BUCKET_NAME
        s3_filename = key.split("/")[-1]
        directory_path = Path(Config.TMP_DIR, self.account, str(self._provider_type), str(self._provider_uuid))
        directory_path.mkdir(parents=True, exist_ok=True)
        local_s3_filename = utils.get_local_file_name(key)
        msg = f"Local S3 filename: {local_s3_filename}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        full_file_path = directory_path.joinpath(s3_filename)
        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        try:
            s3_resource = utils.get_s3_resource(settings.S3_ACCESS_KEY, settings.S3_SECRET, settings.S3_REGION)
            s3_bucket = s3_resource.Bucket(settings.S3_BUCKET_NAME)
            s3_bucket.download_file(key, full_file_path)
        except ClientError as ex:
            if ex.response["Error"]["Code"] == "NoSuchKey":
                msg = f"Unable to find {s3_filename} in S3 Bucket: {bucket}"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                raise ReportDownloaderNoFileError(msg)
            if ex.response["Error"]["Code"] == "AccessDenied":
                msg = f"Unable to access S3 Bucket {bucket}: (AccessDenied)"
                LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
                raise ReportDownloaderNoFileError(msg)
        file_names.append(full_file_path)

        msg = f"Download complete for {key}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        return full_file_path, s3_etag, dh.today, file_names, date_range
