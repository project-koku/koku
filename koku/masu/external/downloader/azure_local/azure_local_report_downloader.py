#
# Copyright 2019 Red Hat, Inc.
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
"""Azure-Local Report Downloader."""
import hashlib
import logging
import os
import shutil

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.util.azure import common as utils
from masu.util.common import extract_uuids_from_string

DATA_DIR = Config.TMP_DIR
LOG = logging.getLogger(__name__)


class AzureLocalReportDownloader(AzureReportDownloader):
    """Azure Cost and Usage Report Downloader."""

    def __init__(self, task, customer_name, auth_credential, billing_source, report_name=None, **kwargs):
        """
        Constructor.

        Args:
            task             (Object) bound celery object
            customer_name    (String) Name of the customer
            auth_credential  (Dict) Dictionary containing Azure authentication details.
            report_name      (String) Name of the Cost Usage Report to download (optional)
            billing_source   (Dict) Dictionary containing Azure Storage blob details.

        """
        kwargs["is_local"] = True
        super().__init__(task, customer_name, auth_credential, billing_source, report_name, **kwargs)

        self._provider_uuid = kwargs.get("provider_uuid")
        self.customer_name = customer_name.replace(" ", "_")
        self.export_name = billing_source.get("resource_group").get("export_name")
        self.directory = billing_source.get("resource_group").get("directory")
        self.container_name = billing_source.get("storage_account").get("container")
        self.local_storage = billing_source.get("storage_account").get("local_dir")

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
            LOG.error("Unable to find manifest.")
            return manifest

        report_names = os.listdir(local_path)
        sorted_by_modified_date = sorted(report_names, key=lambda file: os.path.getmtime(f"{local_path}/{file}"))
        if sorted_by_modified_date:
            report_name = report_names[0]  # First item on list is most recent

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

        return manifest

    def download_file(self, key, stored_etag=None):
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

        if etag != stored_etag:
            LOG.info("Downloading %s to %s", key, full_file_path)
            shutil.copy2(key, full_file_path)
        LOG.info("Returning full_file_path: %s, etag: %s", full_file_path, etag)
        return full_file_path, etag
