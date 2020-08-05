#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""OCP Report Downloader."""
import datetime
import hashlib
import logging
import os
import shutil

import pandas as pd
from django.conf import settings

from api.common import log_json
from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ocp import common as utils

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR
REPORT_TYPES = {
    "storage_usage": "persistentvolumeclaim_labels",
    "pod_usage": "pod_labels",
    "node_labels": "node_labels",
}
LOG = logging.getLogger(__name__)


def divide_csv_daily(file_path, filename):
    """
    Split local file into daily content.
    """
    daily_files = []
    directory = os.path.dirname(file_path)

    data_frame = pd.read_csv(file_path)
    report_type, _ = utils.detect_type(file_path)
    unique_times = data_frame.interval_start.unique()
    days = list({cur_dt[:10] for cur_dt in unique_times})
    daily_data_frames = [
        {"data_frame": data_frame[data_frame.interval_start.str.contains(cur_day)], "date": cur_day}
        for cur_day in days
    ]

    for daily_data in daily_data_frames:
        day = daily_data.get("date")
        df = daily_data.get("data_frame")
        day_file = f"{report_type}.{day}.csv"
        day_filepath = f"{directory}/{day_file}"
        df.to_csv(day_filepath, index=False, header=True)
        daily_files.append({"filename": day_file, "filepath": day_filepath})
    return daily_files


def create_daily_archives(request_id, account, provider_uuid, filename, filepath, manifest_id, start_date, context={}):
    """
    Create daily CSVs from incoming report and archive to S3.

    Args:
        request_id (str): The request id
        account (str): The account number
        provider_uuid (str): The uuid of a provider
        filename (str): The OCP file name
        filepath (str): The full path name of the file
        manifest_id (int): The manifest identifier
        start_date (Datetime): The start datetime of incoming report
        context (Dict): Logging context dictionary
    """
    daily_file_names = []
    if settings.ENABLE_S3_ARCHIVING:
        daily_files = divide_csv_daily(filepath, filename)
        for daily_file in daily_files:
            # Push to S3
            s3_csv_path = get_path_prefix(account, provider_uuid, start_date, Config.CSV_DATA_TYPE)
            copy_local_report_file_to_s3_bucket(
                request_id,
                s3_csv_path,
                daily_file.get("filepath"),
                daily_file.get("filename"),
                manifest_id,
                start_date,
                context,
            )
            daily_file_names.append(daily_file.get("filename"))
            os.remove(daily_file.get("filepath"))
    return daily_file_names


class OCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """OCP Cost and Usage Report Downloader."""

    def __init__(self, customer_name, auth_credential, bucket, report_name=None, **kwargs):
        """
        Initializer.

        Args:
            customer_name    (String) Name of the customer
            auth_credential  (String) OpenShift cluster ID
            report_name      (String) Name of the Cost Usage Report to download (optional)
            bucket           (String) Not used for OCP

        """
        super().__init__(**kwargs)

        LOG.debug("Connecting to OCP service provider...")

        self.customer_name = customer_name.replace(" ", "_")
        self.report_name = report_name
        self.cluster_id = auth_credential
        self.temp_dir = None
        self.bucket = bucket
        self.context["cluster_id"] = self.cluster_id

    def _get_manifest(self, date_time):
        dates = utils.month_date_range(date_time)
        directory = f"{REPORTS_DIR}/{self.cluster_id}/{dates}"
        msg = f"Looking for manifest at {directory}"
        LOG.info(log_json(self.request_id, msg, self.context))
        report_meta = utils.get_report_details(directory)
        return report_meta

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
        report_dict = {}
        manifest = self._get_manifest(date)

        if manifest == {}:
            return report_dict

        manifest_id = self._prepare_db_manifest_record(manifest)
        self._remove_manifest_file(date)

        if manifest:
            report_dict["manifest_id"] = manifest_id
            report_dict["assembly_id"] = manifest.get("uuid")
            report_dict["compression"] = UNCOMPRESSED
            files_list = []
            for key in manifest.get("files"):
                key_full_path = (
                    f"{REPORTS_DIR}/{self.cluster_id}/{utils.month_date_range(date)}/{os.path.basename(key)}"
                )

                file_dict = {"key": key_full_path, "local_file": self.get_local_file_for_report(key_full_path)}
                files_list.append(file_dict)

            report_dict["files"] = files_list
        return report_dict

    def _remove_manifest_file(self, date_time):
        """Clean up the manifest file after extracting information."""
        dates = utils.month_date_range(date_time)
        directory = f"{REPORTS_DIR}/{self.cluster_id}/{dates}"

        manifest_path = "{}/{}".format(directory, "manifest.json")
        try:
            os.remove(manifest_path)
            msg = f"Deleted manifest file at {directory}"
            LOG.debug(log_json(self.request_id, msg, self.context))
        except OSError:
            msg = f"Could not delete manifest file at {directory}"
            LOG.info(log_json(self.request_id, msg, self.context))

        return None

    def get_report_for(self, date_time):
        """
        Get OCP usage report files corresponding to a date.

        Args:
            date_time (DateTime): Start date of the usage report.

        Returns:
            ([]) List of file paths for a particular report.

        """
        dates = utils.month_date_range(date_time)
        msg = f"Looking for cluster {self.cluster_id} report for date {str(dates)}"
        LOG.debug(log_json(self.request_id, msg, self.context))
        directory = f"{REPORTS_DIR}/{self.cluster_id}/{dates}"

        manifest = self._get_manifest(date_time)
        msg = f"manifest found: {str(manifest)}"
        LOG.info(log_json(self.request_id, msg, self.context))

        reports = []
        for file in manifest.get("files", []):
            report_full_path = os.path.join(directory, file)
            reports.append(report_full_path)

        return reports

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download an OCP usage file.

        Args:
            key (str): The OCP file name.

        Returns:
            (String): The path and file name of the saved file

        """
        local_filename = utils.get_local_file_name(key)

        directory_path = f"{DATA_DIR}/{self.customer_name}/ocp/{self.cluster_id}"
        full_file_path = f"{directory_path}/{local_filename}"

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        etag_hasher = hashlib.new("ripemd160")
        etag_hasher.update(bytes(local_filename, "utf-8"))
        ocp_etag = etag_hasher.hexdigest()

        if ocp_etag != stored_etag or not os.path.isfile(full_file_path):
            msg = f"Downloading {key} to {full_file_path}"
            LOG.info(log_json(self.request_id, msg, self.context))
            shutil.move(key, full_file_path)

        create_daily_archives(
            self.request_id,
            self.account,
            self._provider_uuid,
            local_filename,
            full_file_path,
            manifest_id,
            start_date,
            self.context,
        )
        return full_file_path, ocp_etag

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("uuid")

        date_range = utils.month_date_range(manifest.get("date"))
        billing_str = date_range.split("-")[0]
        billing_start = datetime.datetime.strptime(billing_str, "%Y%m%d")

        num_of_files = len(manifest.get("files", []))
        return self._process_manifest_db_record(assembly_id, billing_start, num_of_files)
