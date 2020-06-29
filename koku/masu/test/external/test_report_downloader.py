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
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from model_bakery import baker

from api.models import Provider
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderError
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.external.report_downloader import ReportDownloaderError
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

FAKE = Faker()


class MockAccessor:
    def __init__(self, *args, **kwargs):
        pass

    def get_etag(self):
        return uuid4().hex

    def update(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReportDownloaderTest(MasuTestCase):
    """Test Cases for the ReportDownloader object."""

    def setUp(self):
        """Set up each test case."""
        super().setUp()
        self.fake_creds = fake_arn(service="iam", generate_account_id=True)
        self.mock_task = Mock(request=Mock(id=str(FAKE.uuid4()), return_value={}))

    def create_downloader(self, provider_type):
        """
        Create a ReportDownloader with some faked inputs.

        Args:
            provider_type (str): the provider type (e.g. PROVIDER_AWS)

        Returns:
            ReportDownloader instance.

        """
        downloader = ReportDownloader(
            task=self.mock_task,
            customer_name=FAKE.name(),
            access_credential=self.fake_creds,
            report_source=FAKE.slug(),
            report_name=FAKE.slug(),
            provider_type=provider_type,
            provider_uuid=uuid4(),
            cache_key=FAKE.word(),
        )
        return downloader

    def assertDownloaderSetsProviderDownloader(self, provider_type, downloader_class):
        """
        Assert initializing ReportDownloader sets the expected provider's downloader class.

        Args:
            provider_type (str): the provider type (e.g. PROVIDER_AWS)
            downloader_class (class): the expected downloader class

        """
        downloader = self.create_downloader(provider_type)
        self.assertIsNotNone(downloader._downloader)
        self.assertIsInstance(downloader._downloader, downloader_class)

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_init_with_aws(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the AWS downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_AWS, AWSReportDownloader)
        mock_downloader_init.assert_called()

    @patch(
        "masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader.__init__",
        return_value=None,
    )
    def test_init_with_aws_local(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the AWS-local downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_AWS_LOCAL, AWSLocalReportDownloader)
        mock_downloader_init.assert_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader.__init__", return_value=None)
    def test_init_with_azure(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the Azure downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_AZURE, AzureReportDownloader)
        mock_downloader_init.assert_called()

    @patch(
        "masu.external.downloader.azure_local.azure_local_report_downloader.AzureLocalReportDownloader.__init__",
        return_value=None,
    )
    def test_init_with_azure_local(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the Azure-local downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_AZURE_LOCAL, AzureLocalReportDownloader)
        mock_downloader_init.assert_called()

    @patch("masu.external.downloader.gcp.gcp_report_downloader.GCPReportDownloader.__init__", return_value=None)
    def test_init_with_gcp(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the GCP downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_GCP, GCPReportDownloader)
        mock_downloader_init.assert_called()

    @patch("masu.external.downloader.ocp.ocp_report_downloader.OCPReportDownloader.__init__", return_value=None)
    def test_init_with_ocp(self, mock_downloader_init):
        """Assert ReportDownloader creation sets the OCP downloader."""
        self.assertDownloaderSetsProviderDownloader(Provider.PROVIDER_OCP, OCPReportDownloader)
        mock_downloader_init.assert_called()

    @patch("masu.external.report_downloader.ReportDownloader._set_downloader", side_effect=AWSReportDownloaderError)
    def test_init_with_downloader_exception(self, mock_downloader_init):
        """Assert ReportDownloaderError is raised when _set_downloader raises an exception."""
        with self.assertRaises(ReportDownloaderError):
            self.create_downloader(Provider.PROVIDER_AWS)
        mock_downloader_init.assert_called()

    def test_invalid_provider_type(self):
        """Assert ReportDownloaderError is raised when given an invalid account source."""
        with self.assertRaises(ReportDownloaderError):
            self.create_downloader(FAKE.slug())

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_get_reports_error(self, mock_downloader_init):
        """Assert ReportDownloaderError is raised when get_reports raises an exception."""
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        mock_downloader_init.assert_called()
        with patch.object(AWSReportDownloader, "get_report_context_for_date", side_effect=Exception("some error")):
            with self.assertRaises(ReportDownloaderError):
                downloader.get_reports()

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_is_report_processed(self, mock_downloader_init):
        """Test if given report_name has been processed.

        1. look for non-existent report-name in DB: `is_report_processed` returns False.
        2. look for existing report-name with null last_completed_datetime: `is_report_processed` returns False.
        3. look for existing report-name with not null last_completed_datetime: `is_report_processed` returns True.

        """
        manifest_id = 99
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        report_name = FAKE.slug()
        self.assertFalse(downloader.is_report_processed(report_name, manifest_id))

        baker.make(CostUsageReportManifest, id=manifest_id)
        baker.make(
            CostUsageReportStatus, report_name=report_name, manifest_id=manifest_id, last_completed_datetime=None
        )
        self.assertFalse(downloader.is_report_processed(report_name, manifest_id))

        CostUsageReportStatus.objects.update(last_completed_datetime=FAKE.date())
        self.assertTrue(downloader.is_report_processed(report_name, manifest_id))

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.download_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.get_local_file_for_report")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.get_report_context_for_date")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_download_reports(self, mock_dl_init, mock_dl_context, mock_dl_local_files, mock_dl_download):
        """Test download_reports.

        The downloader will be looking for 3 files:
            file-1.csv.gz: File is done processing -> do not append file
            file-2.csv.gz: File is not recorded in db -> append file
            file-3.csv.gz: File is not done processing -> append file

        This test checks that the 2 files are correctly returned.

        """
        manifest_id = 99
        report_context = {"files": ["file-1.csv.gz", "file-2.csv.gz", "file-3.csv.gz"], "manifest_id": manifest_id}
        mock_dl_context.return_value = report_context
        mock_dl_local_files.side_effect = lambda x: x
        mock_dl_download.side_effect = lambda x, y, manifest_id, start_date: (x, y)

        baker.make(CostUsageReportManifest, id=manifest_id)
        baker.make(
            CostUsageReportStatus,
            report_name=report_context.get("files")[0],
            manifest_id=manifest_id,
            last_completed_datetime=FAKE.date(),
        )
        baker.make(
            CostUsageReportStatus,
            report_name=report_context.get("files")[2],
            manifest_id=manifest_id,
            last_completed_datetime=None,
        )

        downloader = self.create_downloader(Provider.PROVIDER_AWS)

        with patch("masu.external.report_downloader.ReportStatsDBAccessor", side_effect=MockAccessor):
            result = downloader.download_report(FAKE.date())
            result_file_list = [res.get("file") for res in result]
            self.assertEqual(len(result), 2)
            self.assertNotIn(report_context.get("files")[0], result_file_list)
            self.assertIn(report_context.get("files")[1], result_file_list)
            self.assertIn(report_context.get("files")[2], result_file_list)
