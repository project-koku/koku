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

from dateutil.relativedelta import relativedelta

from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER)
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.ocp_local.ocp_local_report_downloader import OCPLocalReportDownloader


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

        if self.provider_type == AWS_LOCAL_SERVICE_PROVIDER:
            return AWSLocalReportDownloader(customer_name=self.customer_name,
                                            auth_credential=self.credential,
                                            bucket=self.cur_source,
                                            report_name=self.report_name)

        if self.provider_type == OCP_LOCAL_SERVICE_PROVIDER:
            return OCPLocalReportDownloader(customer_name=self.customer_name,
                                            auth_credential=self.credential,
                                            bucket=self.cur_source,
                                            report_name=self.report_name)

        return None

    def get_reports(self, number_of_months=1):
        """
        Download cost usage reports.

        Args:
            (Int) Number of monthly reports to download.

        Returns:
            (List) List of filenames downloaded.

        """
        reports = []
        try:
            current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)
            for month in reversed(range(number_of_months)):
                calculated_month = current_month + relativedelta(months=-month)
                reports = reports + self._downloader.download_report(calculated_month)
        except Exception as err:
            raise ReportDownloaderError(str(err))
        return reports
