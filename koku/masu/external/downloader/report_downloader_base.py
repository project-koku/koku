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
"""Report Downloader."""
import logging
from tempfile import mkdtemp

from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor

# from masu.processor.worker_cache import WorkerCache

LOG = logging.getLogger(__name__)


class ReportDownloaderBase:
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    def __init__(self, task, download_path=None, **kwargs):
        """
        Create a downloader.

        Args:
            task          (Object) bound celery object
            download_path (String) filesystem path to store downloaded files

        Kwargs:
            customer_name     (String) customer name
            access_credential (Dict) provider access credentials
            report_source     (String) cost report source
            provider_type     (String) cloud provider type
            provider_uuid     (String) cloud provider uuid
            report_name       (String) cost report name

        """
        self._task = task

        if download_path:
            self.download_path = download_path
        else:
            self.download_path = mkdtemp(prefix="masu")
        self.worker_cache = None  # WorkerCache()
        self._cache_key = kwargs.get("cache_key")
        self._provider_uuid = None
        self._provider_uuid = kwargs.get("provider_uuid")

    def _get_existing_manifest_db_id(self, assembly_id):
        """Return a manifest DB object if it exists."""
        manifest_id = None
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)
            if manifest:
                manifest_id = manifest.id
        return manifest_id

    def check_if_manifest_should_be_downloaded(self, assembly_id):
        """Check if we should download this manifest.

        We first check if we have a database record of this manifest.
        That would indicate that we have already downloaded and at least
        begun processing. We then check the last completed time for
        a file in this manifest. This second check is to cover the case
        when we did not complete processing and need to re-downlaod and
        process the manifest.

        Returns True if the manifest should be downloaded and processed.
        """
        if self._cache_key and self.worker_cache and self.worker_cache.task_is_running(self._cache_key):
            msg = f"{self._cache_key} is currently running."
            LOG.info(msg)
            return False
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)

            if manifest:
                manifest_id = manifest.id
                # check if `last_completed_datetime` is null for any report in the manifest.
                # if nulls exist, report processing is not complete and reports should be downloaded.
                need_to_download = manifest_accessor.is_last_completed_datetime_null(manifest_id)
                if need_to_download and self.worker_cache:
                    self.worker_cache.add_task_to_cache(self._cache_key)
                return need_to_download

        # The manifest does not exist, this is the first time we are
        # downloading and processing it.
        if self.worker_cache:
            self.worker_cache.add_task_to_cache(self._cache_key)
        return True

    def _process_manifest_db_record(self, assembly_id, billing_start, num_of_files):
        """Insert or update the manifest DB record."""
        LOG.info("Inserting/updating manifest in database for assembly_id: %s", assembly_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_entry = manifest_accessor.get_manifest(assembly_id, self._provider_uuid)

            if not manifest_entry:
                LOG.info("No manifest entry found in database. Adding for bill period start: %s", billing_start)
                manifest_dict = {
                    "assembly_id": assembly_id,
                    "billing_period_start_datetime": billing_start,
                    "num_total_files": num_of_files,
                    "provider_uuid": self._provider_uuid,
                    "task": self._task.request.id,
                }
                manifest_entry = manifest_accessor.add(**manifest_dict)

            manifest_accessor.mark_manifest_as_updated(manifest_entry)
            manifest_id = manifest_entry.id

        return manifest_id
