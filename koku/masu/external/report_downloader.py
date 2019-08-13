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

import logging

from dateutil.relativedelta import relativedelta

from masu.database.report_stats_db_accessor import ReportStatsDBAccessor
from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader


LOG = logging.getLogger(__name__)


class ReportDownloaderError(Exception):
    """Report Downloader error."""


# pylint: disable=too-few-public-methods
# pylint: disable=too-many-arguments
class ReportDownloader:
    """Interface for masu to use to get CUR accounts."""

    def __init__(self, customer_name, access_credential, report_source,
                 provider_type, provider_id, report_name=None):
        """Set the downloader based on the backend cloud provider."""
        self.customer_name = customer_name
        self.credential = access_credential
        self.cur_source = report_source
        self.report_name = report_name
        self.provider_type = provider_type
        self.provider_id = provider_id
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
                                       report_name=self.report_name,
                                       provider_id=self.provider_id)

        if self.provider_type == AWS_LOCAL_SERVICE_PROVIDER:
            return AWSLocalReportDownloader(customer_name=self.customer_name,
                                            auth_credential=self.credential,
                                            bucket=self.cur_source,
                                            report_name=self.report_name,
                                            provider_id=self.provider_id)

        if self.provider_type == AWS_LOCAL_SERVICE_PROVIDER:
            return AzureReportDownloader(customer_name=self.customer_name,
                                         auth_credential=self.credential,
                                         bucket=self.cur_source,
                                         report_name=self.report_name,
                                         provider_id=self.provider_id)

        if self.provider_type in (OPENSHIFT_CONTAINER_PLATFORM,
                                  OCP_LOCAL_SERVICE_PROVIDER):
            return OCPReportDownloader(customer_name=self.customer_name,
                                       auth_credential=self.credential,
                                       bucket=self.cur_source,
                                       report_name=self.report_name,
                                       provider_id=self.provider_id)

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
                reports = reports + self.download_report(calculated_month)
        except Exception as err:
            raise ReportDownloaderError(str(err))
        return reports

    def download_report(self, date_time):
        """
        Download CUR for a given date.

        Args:
            date_time (DateTime): The starting datetime object

        Returns:
            ([{}]) List of dictionaries containing file path and compression.

        """
        LOG.info('Attempting to get %s manifest for %s...', self.provider_type, str(date_time))
        report_context = self._downloader.get_report_context_for_date(date_time)
        manifest_id = report_context.get('manifest_id')
        reports = report_context.get('files', [])
        cur_reports = []
        for report in reports:
            report_dictionary = {}
            local_file_name = self._downloader.get_local_file_for_report(report)
            with ReportStatsDBAccessor(local_file_name, manifest_id) as stats_recorder:
                stored_etag = stats_recorder.get_etag()
                file_name, etag = self._downloader.download_file(report, stored_etag)
                stats_recorder.update(etag=etag)

            report_dictionary['file'] = file_name
            report_dictionary['compression'] = report_context.get('compression')
            report_dictionary['start_date'] = date_time
            report_dictionary['assembly_id'] = report_context.get('assembly_id')
            report_dictionary['manifest_id'] = manifest_id
            report_dictionary['provider_id'] = self.provider_id

            cur_reports.append(report_dictionary)
        return cur_reports
