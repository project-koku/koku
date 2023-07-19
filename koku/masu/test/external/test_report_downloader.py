#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportDownloader object."""
from unittest.mock import patch
from uuid import uuid4

from faker import Faker
from model_bakery import baker

from api.models import Provider
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderError
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderNoFileError
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.downloader.gcp.gcp_report_downloader import GCPReportDownloader
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.downloader.report_downloader_base import ReportDownloaderWarning
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

    def create_downloader(self, provider_type):
        """
        Create a ReportDownloader with some faked inputs.

        Args:
            provider_type (str): the provider type (e.g. PROVIDER_AWS)

        Returns:
            ReportDownloader instance.

        """
        return ReportDownloader(
            customer_name=FAKE.name(),
            credentials={"role_arn": self.fake_creds},
            data_source={"data_source": FAKE.slug()},
            report_name=FAKE.slug(),
            provider_type=provider_type,
            provider_uuid=uuid4(),
        )

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

    @patch("masu.external.report_downloader.ReportDownloader._set_downloader", side_effect=ReportDownloaderWarning)
    def test_init_with_downloader_warning(self, mock_downloader_init):
        """Assert ReportDownloaderWarning is raised when _set_downloader raises a ReportDownloaderWarning."""
        with self.assertRaises(ReportDownloaderWarning):
            self.create_downloader(Provider.PROVIDER_GCP)
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
        with patch.object(AWSReportDownloader, "download_file", side_effect=Exception("some error")):
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
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_download_reports(self, mock_dl_init, mock_dl):
        """Test download reports."""
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        manifest_id = 99
        baker.make(CostUsageReportManifest, id=manifest_id)
        assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        compression = "GZIP"
        mock_date = FAKE.date()
        mock_full_file_path = "/full/path/to/file.csv"
        mock_dl.return_value = (mock_full_file_path, "fake_etag", DateAccessor().today(), [], {})

        report_context = {
            "date": mock_date,
            "manifest_id": manifest_id,
            "compression": compression,
            "assembly_id": assembly_id,
            "current_file": f"/my/{assembly_id}/koku-1.csv.gz",
        }

        with patch("masu.external.report_downloader.ReportDownloader.is_report_processed", return_value=False):
            result = downloader.download_report(report_context)
            self.assertEqual(result.get("file"), mock_full_file_path)
            self.assertEqual(result.get("compression"), compression)
            self.assertEqual(result.get("start_date"), mock_date)
            self.assertEqual(result.get("assembly_id"), assembly_id)
            self.assertEqual(result.get("manifest_id"), manifest_id)

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.download_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_download_reports_already_processed(self, mock_dl_init, mock_dl):
        """Test download reports when report is processed."""
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        manifest_id = 99
        baker.make(CostUsageReportManifest, id=manifest_id)
        assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        compression = "GZIP"
        mock_date = FAKE.date()
        mock_full_file_path = "/full/path/to/file.csv"
        mock_dl.return_value = (mock_full_file_path, "fake_etag")

        report_context = {
            "date": mock_date,
            "manifest_id": manifest_id,
            "compression": compression,
            "assembly_id": assembly_id,
            "current_file": f"/my/{assembly_id}/koku-1.csv.gz",
        }

        with patch("masu.external.report_downloader.ReportDownloader.is_report_processed", return_value=True):
            result = downloader.download_report(report_context)
            self.assertEqual(result, {})

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_download_manifest(self, mock_dl):
        """Test download_manifest."""
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        mock_manifest = [{"fake": "manifest"}]
        mock_date = FAKE.date()

        with patch.object(AWSReportDownloader, "get_manifest_context_for_date", return_value=mock_manifest):
            manifest = downloader.download_manifest(mock_date)
            self.assertEqual(manifest, mock_manifest)

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.download_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.__init__", return_value=None)
    def test_download_reports_download_error(self, mock_dl_init, mock_dl):
        """Test download reports when an error is encountered."""
        downloader = self.create_downloader(Provider.PROVIDER_AWS)
        manifest_id = 99
        baker.make(CostUsageReportManifest, id=manifest_id)
        assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        compression = "GZIP"
        mock_date = FAKE.date()
        mock_full_file_path = "/full/path/to/file.csv"
        mock_dl.return_value = (mock_full_file_path, "fake_etag")

        report_context = {
            "date": mock_date,
            "manifest_id": manifest_id,
            "compression": compression,
            "assembly_id": assembly_id,
            "current_file": f"/my/{assembly_id}/koku-1.csv.gz",
        }

        with patch(
            "masu.external.report_downloader.AWSReportDownloader.download_file",
            side_effect=AWSReportDownloaderNoFileError,
        ):
            result = downloader.download_report(report_context)
            self.assertEqual(result, {})
