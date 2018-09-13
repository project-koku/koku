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
"""Provider external interface for koku to consume."""

from masu.external import (AMAZON_WEB_SERVICES, LOCAL_SERVICE_PROVIDER)
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.local.local_report_downloader import LocalReportDownloader


class ReportDownloaderError(Exception):
    """Report Downloader error."""

    pass


# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
class ReportDownloader:
    """Interface for masu to use to get CUR accounts."""

    def __init__(self, customer_name, access_credential, report_source, provider_type,
                 report_name=None):
        """Set the downloader based on the backend cloud provider."""
        self.customer_name = customer_name
        self.credential = access_credential
        self.cur_source = report_source
        self.report_name = report_name
        self.provider_type = provider_type
        try:
            self._downloader = self._set_downloader()
        except Exception as err:
            raise ReportDownloaderError(str(err))

        if not self._downloader:
            raise ReportDownloaderError('Invalid provider type specified.')

    def _set_downloader(self):
        """
        Create the report downloader object.

        Downloader is specific to the provider's cloud service.

        Args:
            None

        Returns:
            (Object) : Some object that is a child of CURAccountsInterface

        """
        if self.provider_type == AMAZON_WEB_SERVICES:
            return AWSReportDownloader(customer_name=self.customer_name,
                                       auth_credential=self.credential,
                                       bucket=self.cur_source,
                                       report_name=self.report_name)

        if self.provider_type == LOCAL_SERVICE_PROVIDER:
            return LocalReportDownloader(customer_name=self.customer_name,
                                         auth_credential=self.credential,
                                         bucket=self.cur_source,
                                         report_name=self.report_name)

        return None

    def get_current_report(self):
        """
        Download the current cost usage report.

        Args:
            None

        Returns:
            (List) List of filenames downloaded.

        """
        try:
            files = self._downloader.download_current_report()
        except Exception as err:
            raise ReportDownloaderError(str(err))
        return files
