#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Downloader interface to be used by Masu."""
from abc import ABC
from abc import abstractmethod


class DownloaderInterface(ABC):
    """Masu interface definition to download cost usage reports."""

    @abstractmethod
    def get_manifest_context_for_date(self, date):
        """
        Get the manifest report context for a provided date.

        Args:
            date (Date): The starting datetime object

        Returns:
            ({}) Dictionary containing the following keys:
                manifest_id - (String): Manifest ID for ReportManifestDBAccessor
                assembly_id - (String): UUID identifying report file
                compression - (String): Report compression format
                files       - ([{"key": full_file_path "local_file": "local file name"}]): List of report files.

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
