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

"""Test the ReportDownloader object."""

from unittest.mock import patch

from masu.external import (
    AWS_LOCAL_SERVICE_PROVIDER,
    AMAZON_WEB_SERVICES,
    AZURE,
    AZURE_LOCAL_SERVICE_PROVIDER,
    OPENSHIFT_CONTAINER_PLATFORM,
)
from masu.external.downloader.aws.aws_report_downloader import (
    AWSReportDownloader,
    AWSReportDownloaderError,
)
from masu.external.report_downloader import ReportDownloader, ReportDownloaderError

from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


class FakeDownloader:
    pass


class ReportDownloaderTest(MasuTestCase):
    """Test Cases for the ReportDownloader object."""

    file_list = [
        '/var/tmp/masu/region/aws/catch-clearly.csv',
        '/var/tmp/masu/base/aws/professor-hour-industry-television.csv',
    ]

    def setUp(self):
        super().setUp()
        self.fake_creds = fake_arn(service='iam', generate_account_id=True)

    @patch(
        'masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__',
        return_value=None,
    )
    def test_initializer_aws(self, fake_downloader):
        """Test to initializer"""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider_id,
        )
        self.assertIsNotNone(downloader._downloader)

    @patch(
        'masu.external.downloader.ocp.ocp_report_downloader.OCPReportDownloader.__init__',
        return_value=None,
    )
    def test_initializer_ocp(self, fake_downloader):
        """Test to initializer"""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=OPENSHIFT_CONTAINER_PLATFORM,
            provider_id=self.ocp_provider_id,
        )
        self.assertIsNotNone(downloader._downloader)

    @patch(
        'masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader.__init__',
        return_value=None,
    )
    def test_initializer_ocp(self, fake_downloader):
        """Test to initializer"""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=OPENSHIFT_CONTAINER_PLATFORM,
            provider_id=self.ocp_provider_id,
        )
        self.assertIsNotNone(downloader._downloader)

    @patch(
        'masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader.__init__',
        return_value=None,
    )
    def test_initializer_azure(self, fake_downloader):
        """Test to initializer for Azure downloader"""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=AZURE,
            provider_id=self.azure_provider_id,
        )
        self.assertIsNotNone(downloader._downloader)

    @patch(
        'masu.external.downloader.azure_local.azure_local_report_downloader.AzureLocalReportDownloader.__init__',
        return_value=None,
    )
    def test_initializer_azure(self, fake_downloader):
        """Test to initializer for Azure downloader"""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=AZURE_LOCAL_SERVICE_PROVIDER,
            provider_id=self.azure_provider_id,
        )
        self.assertIsNotNone(downloader._downloader)

    @patch(
        'masu.external.report_downloader.ReportDownloader._set_downloader',
        side_effect=AWSReportDownloaderError,
    )
    def test_initializer_downloader_exception(self, fake_downloader):
        """Test to initializer where _set_downloader throws exception"""
        with self.assertRaises(ReportDownloaderError):
            ReportDownloader(
                customer_name='customer name',
                access_credential=self.fake_creds,
                report_source='hereiam',
                report_name='bestreport',
                provider_type=AMAZON_WEB_SERVICES,
                provider_id=self.aws_provider_id,
            )

    def test_invalid_provider_type(self):
        """Test that error is thrown with invalid account source."""

        with self.assertRaises(ReportDownloaderError):
            ReportDownloader(
                customer_name='customer name',
                access_credential=self.fake_creds,
                report_source='hereiam',
                report_name='bestreport',
                provider_type='unknown',
                provider_id=self.aws_provider_id,
            )

    @patch(
        'masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__',
        return_value=None,
    )
    def test_get_reports_error(self, fake_downloader):
        """Test get_reports function with error."""
        downloader = ReportDownloader(
            customer_name='customer name',
            access_credential=self.fake_creds,
            report_source='hereiam',
            report_name='bestreport',
            provider_type=AMAZON_WEB_SERVICES,
            provider_id=self.aws_provider_id,
        )
        with patch.object(
            AWSReportDownloader,
            'get_report_context_for_date',
            side_effect=Exception('some error'),
        ):
            with self.assertRaises(ReportDownloaderError):
                downloader.get_reports()
