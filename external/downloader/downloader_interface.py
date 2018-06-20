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

from abc import ABC, abstractmethod


# pylint: disable=too-few-public-methods
class DownloaderInterface(ABC):
    """Masu interface definition to download cost usage reports."""

    @abstractmethod
    def download_current_report(self):
        """
        Download the current cost usage report.

        Implemented by a downloader class.  Must return a list of
        full path of CUR files that are part of the cost usage report.

        Args:
            None

        Returns:
            (List) List of full local file paths to CUR files.

        """
        pass
