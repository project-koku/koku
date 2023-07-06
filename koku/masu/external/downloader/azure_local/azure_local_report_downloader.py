#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure-Local Report Downloader."""
import datetime
import hashlib
import logging
import os
import shutil

from api.common import log_json
from api.provider.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.util.aws.common import copy_local_report_file_to_s3_bucket
from masu.util.aws.common import remove_files_not_in_set_from_s3_bucket
from masu.util.azure import common as utils
from masu.util.common import extract_uuids_from_string
from masu.util.common import get_path_prefix

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureLocalReportDownloader(AzureReportDownloader):
    """Azure Cost and Usage Report Downloader."""

    def __init__(self, customer_name, credentials, data_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            customer_name    (String) Name of the customer
            credentials      (Dict) Dictionary containing Azure credentials details.
            report_name      (String) Name of the Cost Usage Report to download (optional)
            data_source      (Dict) Dictionary containing Azure Storage blob details.

        """
        kwargs["is_local"] = True
        super().__init__(customer_name, credentials, data_source, report_name, **kwargs)

        self._provider_uuid = kwargs.get("provider_uuid")
        self.customer_name = customer_name.replace(" ", "_")
        self.export_name = data_source.get("resource_group").get("export_name")
        self.directory = data_source.get("resource_group").get("directory")
        self.container_name = data_source.get("storage_account").get("container")
        self.local_storage = data_source.get("storage_account").get("local_dir")

    def _get_manifest(self, date_time):
        """
        Download and return the CUR manifest for the given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            (Dict): A dict-like object serialized from JSON data.

        """
        report_path = self._get_report_path(date_time)
        manifest = {}

        local_path = f"{self.local_storage}/{self.container_name}/{report_path}"

        if not os.path.exists(local_path):
            msg = f"Unable to find manifest: {local_path}."
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            return manifest, None

        manifest_modified_timestamp = None
        report_names = os.listdir(local_path)
        sorted_by_modified_date = sorted(report_names, key=lambda file: os.path.getmtime(f"{local_path}/{file}"))
        if sorted_by_modified_date:
            report_name = report_names[0]  # First item on list is most recent
            full_file_path = f"{local_path}/{report_name}"
            manifest_modified_timestamp = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))

        try:
            manifest["assemblyId"] = extract_uuids_from_string(report_name).pop()
        except IndexError:
            message = f"Unable to extract assemblyID from {report_name}"
            raise AzureReportDownloaderError(message)

        billing_period = {
            "start": (report_path.split("/")[-1]).split("-")[0],
            "end": (report_path.split("/")[-1]).split("-")[1],
        }
        manifest["billingPeriod"] = billing_period
        manifest["reportKeys"] = [f"{local_path}/{report_name}"]
        manifest["Compression"] = UNCOMPRESSED

        return manifest, manifest_modified_timestamp

    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a file from Azure bucket.

        Args:
            key (str): The object key identified.

        Returns:
            (String): The path and file name of the saved file

        """
        local_filename = utils.get_local_file_name(key)
        full_file_path = f"{self._get_exports_data_directory()}/{local_filename}"

        etag_hasher = hashlib.new("ripemd160")
        etag_hasher.update(bytes(local_filename, "utf-8"))
        etag = etag_hasher.hexdigest()

        file_creation_date = None
        if etag != stored_etag:
            msg = f"Downloading {key} to {full_file_path}"
            LOG.info(log_json(self.request_id, msg=msg, context=self.context))
            shutil.copy2(key, full_file_path)
            file_creation_date = datetime.datetime.fromtimestamp(os.path.getmtime(full_file_path))
            # Push to S3
            s3_csv_path = get_path_prefix(
                self.account, Provider.PROVIDER_AZURE, self._provider_uuid, start_date, Config.CSV_DATA_TYPE
            )
            copy_local_report_file_to_s3_bucket(
                self.request_id, s3_csv_path, full_file_path, local_filename, manifest_id, self.context
            )

            manifest_accessor = ReportManifestDBAccessor()
            manifest = manifest_accessor.get_manifest_by_id(manifest_id)

            if not manifest_accessor.get_s3_csv_cleared(manifest):
                remove_files_not_in_set_from_s3_bucket(self.request_id, s3_csv_path, manifest_id)
                manifest_accessor.mark_s3_csv_cleared(manifest)

        msg = f"Returning full_file_path: {full_file_path}, etag: {etag}"
        LOG.info(log_json(self.request_id, msg=msg, context=self.context))
        return full_file_path, etag, file_creation_date, [], {}
