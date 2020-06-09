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
"""Downloader interface to be used by Masu."""
from abc import ABC
from abc import abstractmethod


class DownloaderInterface(ABC):
    """Masu interface definition to download cost usage reports."""

    @abstractmethod
    def get_report_context_for_date(self, date_time):
        """
        Get the report context for a provided date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([]): List of report files.

        """

    @abstractmethod
    def get_local_file_for_report(self, report):
        """
        Return the temporary volume full file path for a report file.

        Args:
            report (String): Report file from manifest.

        Returns:
            (String) Full path to report file.

        """

    @abstractmethod
    def download_file(self, key, stored_etag=None, manifest_id=None, start_date=None):
        """
        Download a report file given a provider-specific key.

        Args:
            key (String): A key that can locate a report file.
            stored_etag (String): ReportStatsDBAccessor file identifier.
            manifest_id (String): Report manifest identifier
            start_date (DateTime): Report start date time

        Returns:
            (String, String) Full local file path to report, etag value.

        """
