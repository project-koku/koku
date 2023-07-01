#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Report Downloader."""
import datetime
import hashlib
import logging
import os
import shutil

import pandas as pd

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.downloader_interface import DownloaderInterface
from masu.external.downloader.report_downloader_base import ReportDownloaderBase
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.common import get_path_prefix
from masu.util.ocp import common as utils

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

LOG = logging.getLogger(__name__)


def divide_csv_daily(file_path, filename):
    """
    Split local file into daily content.
    """
    daily_files = []
    directory = os.path.dirname(file_path)

    try:
        data_frame = pd.read_csv(file_path)
    except Exception as error:
        LOG.error(f"File {file_path} could not be parsed. Reason: {str(error)}")
        raise error

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


def create_daily_archives(tracing_id, account, provider_uuid, filename, filepath, manifest_id, start_date, context={}):
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
    if context.get("version"):
        daily_files = [{"filepath": filepath, "filename": filename}]
    else:
        daily_files = divide_csv_daily(filepath, filename)
    for daily_file in daily_files:
        # Push to S3
        s3_csv_path = get_path_prefix(account, Provider.PROVIDER_OCP, provider_uuid, start_date, Config.CSV_DATA_TYPE)
        copy_local_report_file_to_s3_bucket(
            tracing_id,
            s3_csv_path,
            daily_file.get("filepath"),
            daily_file.get("filename"),
            manifest_id,
            start_date,
            context,
        )
        daily_file_names.append(daily_file.get("filepath"))
    return daily_file_names


def process_cr(report_meta):
    """
    Process the manifest info.

    Args:
        report_meta (Dict): The metadata from the manifest

    Returns:
        manifest_info (Dict): Dictionary containing the following:
            airgapped: (Bool or None)
            version: (str or None)
            certified: (Bool or None)
            channel: (str or None)
            errors: (Dict or None)
    """
    LOG.info(log_json(report_meta.get("tracing_id"), msg="Processing the manifest"))
    operator_versions = {
        "5806b175a7b31e6ee112c798fa4222cc652b40a6": "costmanagement-metrics-operator:2.0.0",
        "e3450f6e3422b6c39c582028ec4ce19b8d09d57d": "costmanagement-metrics-operator:1.2.0",
        "61099eb07331b140cf66104bc1056c3f3211c94e": "costmanagement-metrics-operator:1.1.9",
        "6d38c76be52e5981eaf19377a559dc681f1be405": "costmanagement-metrics-operator:1.1.8",
        "0159d5e55ce6a5a18f989e6f04146f47983ebdf3": "costmanagement-metrics-operator:1.1.7",
        "2a702a3aac89f724a08b08650b77a0bd33f5b5e5": "costmanagement-metrics-operator:1.1.6",
        "f8d1f7c5d8685f758ecc36a14aca3b6b86614613": "costmanagement-metrics-operator:1.1.5",
        "77ec351f8d332796dc522e5623f1200c2fab4042": "costmanagement-metrics-operator:1.1.4",
        "084bca2e1c48caab18c237453c17ceef61747fe2": "costmanagement-metrics-operator:1.1.3",
        "6f10d07e3af3ea4f073d4ffda9019d8855f52e7f": "costmanagement-metrics-operator:1.1.0",
        "fd764dcd7e9b993025f3e05f7cd674bb32fad3be": "costmanagement-metrics-operator:1.0.0",
        "26502d500672019af5c11319b558dec873409e38": "koku-metrics-operator:v2.0.0",
        "2acd43ccec2d6fe6ec292aece951b3cf0b869071": "koku-metrics-operator:v1.2.0",
        "ebe8dab6aebfeacf9a3428d66cc8be7da682c2ad": "koku-metrics-operator:v1.1.9",
        "ccc78b4fd4b63a6cb1516574d5e38a9b1078ea16": "koku-metrics-operator:v1.1.8",
        "2003f0ea23efc49b7ba1337a16b1c90c6899824b": "koku-metrics-operator:v1.1.7",
        "45cc7a72ced124a267acf0976d90504f134e1076": "koku-metrics-operator:v1.1.6",
        "2c52da1481d0c90099e130f6989416cdd3cd7b5a": "koku-metrics-operator:v1.1.5",
        "12b9463a9501f8e9acecbfa4f7e7ae7509d559fa": "koku-metrics-operator:v1.1.4",
        "3430d17b8ad52ee912fc816da6ed31378fd28367": "koku-metrics-operator:v1.1.3",
        "02f315aa5a7f0bf5adecd3668b0a769799b54be8": "koku-metrics-operator:v1.1.2",
        "7c413e966e2ec0a709f5a25cbf5a487c646306d1": "koku-metrics-operator:v1.1.1",
        "f73a992e7b2fc19028b31c7fb87963ae19bba251": "koku-metrics-operator:v0.9.8",
        "d37e6d6fd90d65b0d6794347f5fe00a472ce9d33": "koku-metrics-operator:v0.9.7",
        "1019682a6aa1eeb7533724b07d98cfb54dbe0e94": "koku-metrics-operator:v0.9.6",
        "513e7dffddb6ecc090b9e8f20a2fba2fe8ec6053": "koku-metrics-operator:v0.9.5",
        "eaef8ea323b3531fa9513970078a55758afea665": "koku-metrics-operator:v0.9.4",
        "4f1cc5580da20a11e6dfba50d04d8ae50f2e5fa5": "koku-metrics-operator:v0.9.2",
        "0419bb957f5cdfade31e26c0f03b755528ec0d7f": "koku-metrics-operator:v0.9.1",
        "bfdc1e54e104c2a6c8bf830ab135cf56a97f41d2": "koku-metrics-operator:v0.9.0",
    }
    manifest_info = {
        "cluster_id": report_meta.get("cluster_id"),
        "operator_certified": report_meta.get("certified"),
        "operator_version": operator_versions.get(report_meta.get("version")),
        "cluster_channel": None,
        "operator_airgapped": None,
        "operator_errors": None,
    }
    if cr_status := report_meta.get("cr_status"):
        manifest_info["cluster_channel"] = cr_status.get("clusterVersion")
        manifest_info["operator_airgapped"] = not cr_status.get("upload", {}).get("upload")
        errors = {}
        for case in ["authentication", "packaging", "upload", "prometheus", "source"]:
            if err := cr_status.get(case, {}).get("error"):
                errors[case + "_error"] = err
        manifest_info["operator_errors"] = errors or None

    return manifest_info


class OCPReportDownloader(ReportDownloaderBase, DownloaderInterface):
    """OCP Cost and Usage Report Downloader."""

    def __init__(self, customer_name, credentials, data_source, report_name=None, **kwargs):
        """
        Initializer.

        Args:
            customer_name    (String) Name of the customer
            credentials      (Dict) Credentials containing OpenShift cluster ID
            report_name      (String) Name of the Cost Usage Report to download (optional)
            data_source      (Dict) Not used for OCP

        """
        super().__init__(**kwargs)

        LOG.debug("Connecting to OCP service provider...")

        self.customer_name = customer_name.replace(" ", "_")
        self.report_name = report_name
        self.temp_dir = None
        self.data_source = data_source
        if isinstance(credentials, dict):
            self.cluster_id = credentials.get("cluster_id")
        else:
            self.cluster_id = credentials
        self.context["cluster_id"] = self.cluster_id
        self.manifest = None

    def _get_manifest(self, date_time):
        dates = utils.month_date_range(date_time)
        directory = f"{REPORTS_DIR}/{self.cluster_id}/{dates}"
        msg = f"Looking for manifest at {directory}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
        report_meta = utils.get_report_details(directory)
        self.context["version"] = report_meta.get("version")
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
            LOG.debug(log_json(self.tracing_id, msg=msg, context=self.context))
        except OSError:
            msg = f"Could not delete manifest file at {directory}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

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
        LOG.debug(log_json(self.tracing_id, msg=msg, context=self.context))
        directory = f"{REPORTS_DIR}/{self.cluster_id}/{dates}"

        manifest = self._get_manifest(date_time)
        msg = f"manifest found: {str(manifest)}"
        LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))

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
        if not self.manifest:
            self.manifest = ReportManifestDBAccessor().get_manifest_by_id(manifest_id)
        self.context["version"] = self.manifest.operator_version
        local_filename = utils.get_local_file_name(key)

        directory_path = f"{DATA_DIR}/{self.customer_name}/ocp/{self.cluster_id}"
        full_file_path = f"{directory_path}/{local_filename}"

        # Make sure the data directory exists
        os.makedirs(directory_path, exist_ok=True)
        etag_hasher = hashlib.new("ripemd160")
        etag_hasher.update(bytes(local_filename, "utf-8"))
        ocp_etag = etag_hasher.hexdigest()

        file_creation_date = None
        if ocp_etag != stored_etag or not os.path.isfile(full_file_path):
            msg = f"Downloading {key} to {full_file_path}"
            LOG.info(log_json(self.tracing_id, msg=msg, context=self.context))
            shutil.move(key, full_file_path)
            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

        file_names = create_daily_archives(
            self.tracing_id,
            self.account,
            self._provider_uuid,
            local_filename,
            full_file_path,
            manifest_id,
            start_date,
            self.context,
        )

        return full_file_path, ocp_etag, file_creation_date, file_names, {}

    def get_local_file_for_report(self, report):
        """Get full path for local report file."""
        return utils.get_local_file_name(report)

    def _prepare_db_manifest_record(self, manifest):
        """Prepare to insert or update the manifest DB record."""
        assembly_id = manifest.get("uuid")

        date_range = utils.month_date_range(manifest.get("date"))
        billing_str = date_range.split("-")[0]
        billing_start = datetime.datetime.strptime(billing_str, "%Y%m%d")
        manifest_timestamp = manifest.get("date")
        num_of_files = len(manifest.get("files") or [])
        manifest_info = process_cr(manifest)
        return self._process_manifest_db_record(
            assembly_id, billing_start, num_of_files, manifest_timestamp, **manifest_info
        )
