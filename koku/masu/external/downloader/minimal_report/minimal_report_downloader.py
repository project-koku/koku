#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Minimalist Report Downloader."""
import logging
import os
import uuid

from botocore.exceptions import ClientError

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws import common as utils
from masu.util.common import get_path_prefix


DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class MinimalReportDownloaderNoFileError(Exception):
    """Minimal Report Downloader error for missing file."""


class MinimalReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """
    Minimal Cost and Usage Report Downloader.
    """

    def __init__(self, customer_name, credentials, minimal_reports, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            minimal_reports      (list of strings) List of Minimal reports for processing

        """
        super().__init__(**kwargs)

        arn = credentials.get("role_arn")
        self.customer_name = customer_name.replace(" ", "_")
        self._provider_uuid = kwargs.get("provider_uuid")
        self.minimal_reports = minimal_reports

        LOG.debug("Connecting to AWS...")
        session = utils.get_assume_role_session(utils.AwsArn(arn), "MasuDownloaderSession")
        self.cur = session.client("cur")
        self.s3_client = session.client("s3")

    def get_manifest_context_for_date(self, date):
        """
        Get the manifest context for a provided date.
        For Minimal we don't care about the dates since these are manually posted files.

        Args:
            date (Date): The starting datetime object

        Returns:
            Manifest dict
        """
        manifest_dict = {}
        report_dict = {}
        manifest_dict = self._generate_monthly_pseudo_manifest(date)
        if manifest_dict:
            assembly_id = ":".join([str(self._provider_uuid), str(date)])
            manifest_id = self._process_manifest_db_record(
                assembly_id,
                date.strftime("%Y-%m-%d"),
                len(manifest_dict.get("file_names")),
                date,
            )

            report_dict["manifest_id"] = manifest_id
            report_dict["assembly_id"] = assembly_id
            report_dict["compression"] = manifest_dict.get("compression")
            files_list = [
                {"key": key, "local_file": self.get_local_file_for_report(key)}
                for key in manifest_dict.get("file_names")
            ]
            report_dict["files"] = files_list
        return report_dict

    def _generate_monthly_pseudo_manifest(self, date):
        """
        Generate a dict representing an analog to other providers "manifest" files.

        Minimal does not produce a manifest file for monthly periods. So we check for
        files in the bucket based on what the customer posts.

        Args:
            report_data: Where reports are stored

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
            "file_names": self.minimal_reports,
        }
        LOG.info(f"Manifest Data: {str(manifest_data)}")
        return manifest_data

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download an S3 object to file.

        Args:
            key (str): The S3 object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        if key.startswith("s3://"):
            bucket = key.split("/")[2]
        else:
            bucket = key.split("/")[0]
        s3_file = key.split(f"{bucket}/")[-1]
        s3_filename = key.split("/")[-1]
        directory_path = f"{DATA_DIR}/{self.customer_name}/minimal-reports/aws/{bucket}"
        local_s3_filename = utils.get_local_file_name(key)

        msg = f"Local S3 filename: {s3_filename}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        full_file_path = f"{directory_path}/{s3_filename}"

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        s3_etag = None
        file_creation_date = None
        try:
            s3_file_details = self.s3_client.get_object(Bucket=bucket, Key=s3_file)
            s3_etag = s3_file_details.get("ETag")
            file_creation_date = s3_file_details.get("LastModified")
        except ClientError as ex:
            if ex.response["Error"]["Code"] == "NoSuchKey":
                msg = f"Unable to find {s3_filename} in S3 Bucket: {bucket}"
                LOG.info(log_json(self.tracing_id, msg, self.context))
                raise MinimalReportDownloaderNoFileError(msg)

        msg = f"Downloading key: {s3_file} to file path: {full_file_path}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        self.s3_client.download_file(bucket, s3_file, full_file_path)
        # Push to S3
        s3_csv_path = get_path_prefix(
            self.account, Provider.PROVIDER_AWS, self._provider_uuid, start_date, Config.CSV_DATA_TYPE
        )
        utils.copy_local_report_file_to_s3_bucket(
            self.tracing_id, s3_csv_path, full_file_path, local_s3_filename, manifest_id, start_date, self.context
        )

        manifest_accessor = ReportManifestDBAccessor()
        manifest = manifest_accessor.get_manifest_by_id(manifest_id)

        if not manifest_accessor.get_s3_csv_cleared(manifest):
            utils.remove_files_not_in_set_from_s3_bucket(self.tracing_id, s3_csv_path, manifest_id)
            manifest_accessor.mark_s3_csv_cleared(manifest)

        msg = f"Download complete for {s3_file}"
        LOG.info(log_json(self.tracing_id, msg, self.context))
        return full_file_path, s3_etag, file_creation_date, [], {}

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        local_file_name = report.replace("/", "_")
        return local_file_name
