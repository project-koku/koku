#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Local Report Downloader."""
import datetime
import hashlib
import json
import logging
import os
import re
import shutil

from api.common import log_json
from masu.config import Config
from masu.external.downloader.aws.aws_report_downloader import create_daily_archives
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws import common as utils

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AWSReportDownloaderNoFileError(Exception):
    """AWS Report Downloader error for missing file."""

    pass


class AWSLocalReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """Local Cost and Usage Report Downloader."""

    empty_manifest = {"reportKeys": []}

    def __init__(self, customer_name, credentials, data_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            credentials      (Dict) credentials credential for S3 bucket (RoleARN)
            report_name      (String) Name of the Cost Usage Report to download (optional)
            data_source      (Dict) Name of the S3 bucket containing the CUR

        """
        super().__init__(**kwargs)

        bucket = data_source.get("bucket")

        self.customer_name = customer_name.replace(" ", "_")

        LOG.debug("Connecting to local service provider...")
        prefix, name = self._extract_names(bucket)

        self.report_name = report_name if report_name else name
        self.report_prefix = prefix

        msg = f"Found report name: {self.report_name}, report prefix: {self.report_prefix}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        if self.report_prefix:
            self.base_path = f"{bucket}/{self.report_prefix}/"
        else:
            self.base_path = bucket
        self.bucket_path = bucket
        self.bucket = bucket.replace("/", "_")
        self.credential = credentials

    @property
    def manifest_date_format(self):
        """Set the AWS manifest date format."""
        return "%Y%m%dT000000.000Z"

    def _extract_names(self, bucket):
        """
        Find the report name and prefix given the bucket path.

        Args:
            bucket (String): Path to the local file

        Returns:
            (String, String) report_prefix, report_name

        """
        daterange = r"\d{8}-\d{8}"  # noqa: W605
        full_path = ""
        for item in os.walk(bucket, followlinks=True):
            if not item[2]:
                if any(re.findall(daterange, date) for date in item[1]):
                    full_path = item[0]
                    break
        directories = full_path[len(bucket) :]  # noqa

        report_prefix = None
        report_name = None
        if directories:
            parts = directories.strip("/").split("/")
            report_name = parts.pop()
            report_prefix = parts.pop() if parts else None
        return report_prefix, report_name

    def _get_manifest(self, date_time):
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        manifest = f"{self._get_report_path(date_time)}/{self.report_name}-Manifest.json"

        try:
            manifest_file, _, manifest_modified_timestamp, __, ___ = self.download_file(manifest)
        except AWSReportDownloaderNoFileError as err:
            msg = f"Unable to get report manifest. Reason: {str(err)}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            return "", self.empty_manifest, None

        manifest_json = None
        with open(manifest_file) as manifest_file_handle:
            manifest_json = json.load(manifest_file_handle)

        return manifest_file, manifest_json, manifest_modified_timestamp

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
        manifest_file, manifest, manifest_timestamp = self._get_manifest(date)
        if manifest == self.empty_manifest:
            return report_dict
        manifest_dict = self._prepare_db_manifest_record(manifest)
        self._remove_manifest_file(manifest_file)

        if manifest_dict:
            manifest_id = self._process_manifest_db_record(
                manifest_dict.get("assembly_id"),
                manifest_dict.get("billing_start"),
                manifest_dict.get("num_of_files"),
                manifest_timestamp,
            )

            report_dict["manifest_id"] = manifest_id
            report_dict["assembly_id"] = manifest.get("assemblyId")
            report_dict["compression"] = "GZIP"

            files_list = [
                {
                    "key": f"{self._get_report_path(date)}/{manifest.get('assemblyId')}/{os.path.basename(key)}",
                    "local_file": self.get_local_file_for_report(key),
                }
                for key in manifest.get("reportKeys")
            ]
            report_dict["files"] = files_list
        return report_dict

    def _remove_manifest_file(self, manifest_file):
        """Clean up the manifest file after extracting information."""
        try:
            os.remove(manifest_file)
            msg = f"Deleted manifest file at {manifest_file}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        except OSError:
            msg = f"Could not delete manifest file at {manifest_file}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

        return None

    def _get_report_path(self, date_time):
        """
        Return path of report files.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (String): "/prefix/report_name/YYYYMMDD-YYYYMMDD",
                    example: "/my-prefix/my-report/19701101-19701201"

        """
        report_date_range = utils.month_date_range(date_time)
        return f"{self.base_path}/{self.report_name}/{report_date_range}"

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        clear_parquet = False
        file_names = []
        date_range = {}
        local_s3_filename = utils.get_local_file_name(key)

        directory_path = f"{DATA_DIR}/{self.customer_name}/aws-local/{self.bucket}"
        full_file_path = f"{directory_path}/{local_s3_filename}"

        if not os.path.isfile(key):
            log_msg = f"Unable to locate {key} in {self.bucket_path}"
            raise AWSReportDownloaderNoFileError(log_msg)

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        s3_etag_hasher = hashlib.new("ripemd160")
        s3_etag_hasher.update(bytes(local_s3_filename, "utf-8"))
        s3_etag = s3_etag_hasher.hexdigest()

        file_creation_date = None
        if s3_etag != stored_etag or not os.path.isfile(full_file_path):
            msg = f"Downloading key: {key} to file path: {full_file_path}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            shutil.copy2(key, full_file_path)
            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

            if not key.endswith(".json"):
                file_names, date_range, clear_parquet = create_daily_archives(
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

        return full_file_path, s3_etag, file_creation_date, file_names, date_range, clear_parquet

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("assemblyId")
        billing_str = manifest.get("billingPeriod", {}).get("start")
        billing_start = datetime.datetime.strptime(billing_str, self.manifest_date_format)
        num_of_files = len(manifest.get("reportKeys", []))
        return {"assembly_id": assembly_id, "billing_start": billing_start, "num_of_files": num_of_files}
