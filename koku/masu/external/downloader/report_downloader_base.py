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

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ReportDownloaderBase():
    """
    Download cost reports from a provider.

    Base object class for downloading cost reports from a cloud provider.
    """

    # pylint: disable=unused-argument
    def __init__(self, download_path=None, **kwargs):
        """
        Create a downloader.

        Args:
            download_path (String) filesystem path to store downloaded files
        """
        if download_path:
            self.download_path = download_path
        else:
            self.download_path = mkdtemp(prefix='masu')
        self._provider_id = None
        if 'provider_id' in kwargs:
            self._provider_id = kwargs['provider_id']

    def _process_manifest_db_record(self, assembly_id, billing_start, num_of_files):
        """Insert or update the manifest DB record."""
        LOG.info('Inserting manifest database record for assembly_id: %s', assembly_id)

        with ReportManifestDBAccessor() as manifest_accessor:
            manifest_entry = manifest_accessor.get_manifest(
                assembly_id,
                self._provider_id
            )

            if not manifest_entry:
                LOG.info('No manifest entry found.  Adding for bill period start: %s',
                         billing_start)
                manifest_dict = {
                    'assembly_id': assembly_id,
                    'billing_period_start_datetime': billing_start,
                    'num_total_files': num_of_files,
                    'provider_id': self._provider_id
                }
                manifest_entry = manifest_accessor.add(**manifest_dict)

            manifest_accessor.mark_manifest_as_updated(manifest_entry)
            manifest_id = manifest_entry.id

        return manifest_id
