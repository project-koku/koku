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
import datetime
import logging
from tempfile import mkdtemp

from koku.celery import app
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external.date_accessor import DateAccessor

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportDownloaderBase():
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    # pylint: disable=unused-argument
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
            self.download_path = mkdtemp(prefix='masu')
        self._provider_uuid = None
        if 'provider_uuid' in kwargs:
            self._provider_uuid = kwargs['provider_uuid']

    def _get_existing_manifest_db_id(self, assembly_id):
        """Return a manifest DB object if it exists."""
        manifest_id = None
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(
                assembly_id,
                self._provider_uuid
            )
            if manifest:
                manifest_id = manifest.id
        return manifest_id

    def check_task_queues(self, task_id):
        """Check if the provided task id is in the celery queues."""
        # inspect() returns {'worker_name': [{'id': uuid4(), <...>}, {'id': uuid4(), <...>}]}
        inspect = app.control.inspect()

        def unroll(obj):
            """Unwrap list values."""
            return [task.get('id') for tasklist in obj for task in tasklist]

        active = unroll(inspect.active().values())
        reserved = unroll(inspect.reserved().values())
        scheduled = unroll(inspect.scheduled().values())
        if task_id in active + reserved + scheduled:
            return True
        return False

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
        today = DateAccessor().today_with_timezone('UTC')
        last_completed_cutoff = today - datetime.timedelta(hours=1)
        with ReportManifestDBAccessor() as manifest_accessor:
            manifest = manifest_accessor.get_manifest(
                assembly_id,
                self._provider_uuid
            )

            if manifest:
                if manifest.task and self.check_task_queues(manifest.task):
                    # if the previous task is still in the celery queues, it is
                    # probably still running. We should not queue a new download
                    # until it completes.
                    return False
                LOG.info('No task-id found for manifest "%s".', manifest.id)

                manifest_id = manifest.id
                num_processed_files = manifest.num_processed_files
                num_total_files = manifest.num_total_files
                if num_processed_files < num_total_files:
                    completed_datetime = manifest_accessor.get_last_report_completed_datetime(
                        manifest_id
                    )
                    if (completed_datetime and completed_datetime < last_completed_cutoff) or \
                            not completed_datetime:
                        # It has been more than an hour since we processed a file
                        # and we didn't finish processing. Or, if there is a
                        # start time but no completion time recorded.
                        # We should download and reprocess.
                        manifest_accessor.reset_manifest(manifest_id)
                        return True
                # The manifest exists and we have processed all the files.
                # We should not redownload.
                return False
        # The manifest does not exist, this is the first time we are
        # downloading and processing it.
        return True

    def _process_manifest_db_record(self, assembly_id, billing_start, num_of_files):
        """Insert or update the manifest DB record."""
        LOG.info('Inserting manifest database record for assembly_id: %s', assembly_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_entry = manifest_accessor.get_manifest(
                assembly_id,
                self._provider_uuid
            )

            if not manifest_entry:
                LOG.info('No manifest entry found.  Adding for bill period start: %s',
                         billing_start)
                manifest_dict = {
                    'assembly_id': assembly_id,
                    'billing_period_start_datetime': billing_start,
                    'num_total_files': num_of_files,
                    'provider_uuid': self._provider_uuid,
                    'task': self._task.request.id
                }
                manifest_entry = manifest_accessor.add(**manifest_dict)

            manifest_accessor.mark_manifest_as_updated(manifest_entry)
            manifest_id = manifest_entry.id

        return manifest_id
