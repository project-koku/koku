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

from faker import Faker

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
from masu.external.downloader.aws_local.aws_local_report_downloader import (
    AWSLocalReportDownloader,
)
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure_local.azure_local_report_downloader import (
    AzureLocalReportDownloader,
)
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.report_downloader import ReportDownloader, ReportDownloaderError

from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn


FAKE = Faker()


class ReportDownloaderTest(MasuTestCase):
    """Test Cases for the ReportDownloader object."""

    def setUp(self):
        super().setUp()
        self.fake_creds = fake_arn(service='iam', generate_account_id=True)

    def create_downloader(self, provider_type):
        """
        Helper function to create a ReportDownloader with some faked inputs.

        Args:
            provider_type (str): the provider type (e.g. AMAZON_WEB_SERVICES)

        Returns:
            ReportDownloader instance.

        """
        downloader = ReportDownloader(
            customer_name=FAKE.name(),
            access_credential=self.fake_creds,
            report_source=FAKE.slug(),
            report_name=FAKE.slug(),
            provider_type=provider_type,
            provider_id=FAKE.pyint(),
        )
        return downloader

    def assertDownloaderSetsProviderDownloader(self, provider_type, downloader_class):
        """
        Assert initializing ReportDownloader sets the expected provider's downloader class.

        Args:
            provider_type (str): the provider type (e.g. AMAZON_WEB_SERVICES)
            downloader_class (class): the expected downloader class

        """
        downloader = self.create_downloader(provider_type)
        self.assertIsNotNone(downloader._downloader)
        self.assertIsInstance(downloader._downloader, downloader_class)

    @patch(
        'masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__',
        return_value=None,
    )
    def test_init_with_aws(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the AWS downloader."""
        self.assertDownloaderSetsProviderDownloader(
            AMAZON_WEB_SERVICES, AWSReportDownloader
        )
        mock_downloader_init.assert_called()

    @patch(
        'masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader.__init__',
        return_value=None,
    )
    def test_init_with_aws_local(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the AWS-local downloader."""
        self.assertDownloaderSetsProviderDownloader(
            AWS_LOCAL_SERVICE_PROVIDER, AWSLocalReportDownloader
        )
        mock_downloader_init.assert_called()

    @patch(
        'masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader.__init__',
        return_value=None,
    )
    def test_init_with_azure(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the Azure downloader."""
        self.assertDownloaderSetsProviderDownloader(AZURE, AzureReportDownloader)
        mock_downloader_init.assert_called()

    @patch(
        'masu.external.downloader.azure_local.azure_local_report_downloader.AzureLocalReportDownloader.__init__',
        return_value=None,
    )
    def test_init_with_azure_local(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the Azure-local downloader."""
        self.assertDownloaderSetsProviderDownloader(
            AZURE_LOCAL_SERVICE_PROVIDER, AzureLocalReportDownloader
        )
        mock_downloader_init.assert_called()

    @patch(
        'masu.external.downloader.ocp.ocp_report_downloader.OCPReportDownloader.__init__',
        return_value=None,
    )
    def test_init_with_ocp(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the OCP downloader."""
        self.assertDownloaderSetsProviderDownloader(
            OPENSHIFT_CONTAINER_PLATFORM, OCPReportDownloader
        )
        mock_downloader_init.assert_called()

    @patch(
        'masu.external.report_downloader.ReportDownloader._set_downloader',
        side_effect=AWSReportDownloaderError,
    )
    def test_init_with_downloader_exception(self, mock_downloader_init):
        """Assert ReportDownloaderError is raised when _set_downloader raises an exception."""
        with self.assertRaises(ReportDownloaderError):
            self.create_downloader(AMAZON_WEB_SERVICES)
        mock_downloader_init.assert_called()

    def test_invalid_provider_type(self):
        """Assert ReportDownloaderError is raised when given an invalid account source."""
        with self.assertRaises(ReportDownloaderError):
            self.create_downloader(FAKE.slug())

    @patch(
        'masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__',
        return_value=None,
    )
    def test_get_reports_error(self, mock_downloader_init):
        """Assert ReportDownloaderError is raised when get_reports raises an exception."""
        downloader = self.create_downloader(AMAZON_WEB_SERVICES)
        mock_downloader_init.assert_called()
        with patch.object(
            AWSReportDownloader,
            'get_report_context_for_date',
            side_effect=Exception('some error'),
        ):
            with self.assertRaises(ReportDownloaderError):
                downloader.get_reports()
