#
# Copyright 2019 Red Hat, Inc.
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
"""Test the AzureReportDownloader object."""
import shutil
from datetime import datetime
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from faker import Faker

from masu.config import Config
from masu.external import UNCOMPRESSED
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloaderError
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.test import MasuTestCase
from masu.util import common as utils

DATA_DIR = Config.TMP_DIR


class MockAzureService:
    """Mock an azure service."""

    def __init__(self):
        """Initialize a mocked azure service."""
        self.export_name = "costreport"
        self.container = "test_container"
        self.directory = "cost"
        self.test_date = datetime(2019, 8, 15)
        self.month_range = utils.month_date_range(self.test_date)
        self.report_path = f"{self.directory}/{self.export_name}/{self.month_range}"
        self.export_uuid = "9c308505-61d3-487c-a1bb-017956c9170a"
        self.export_file = f"{self.export_name}_{self.export_uuid}.csv"
        self.export_etag = "absdfwef"
        self.export_key = f"{self.report_path}/{self.export_file}"
        self.bad_test_date = datetime(2019, 7, 15)
        self.bad_month_range = utils.month_date_range(self.bad_test_date)
        self.bad_report_path = f"{self.directory}/{self.export_name}/{self.bad_month_range}"

    def describe_cost_management_exports(self):
        """Describe cost management exports."""
        return [{"name": self.export_name, "container": self.container, "directory": self.directory}]

    def get_latest_cost_export_for_path(self, report_path, container_name):
        """Get exports for path."""

        class BadExport:
            name = self.export_name

        class Export:
            name = self.export_file

        if report_path == self.report_path:
            mock_export = Export()
        elif report_path == self.bad_report_path:
            mock_export = BadExport()
        else:
            message = f"No cost report found in container {container_name} for " f"path {report_path}."
            raise AzureCostReportNotFound(message)
        return mock_export

    def get_cost_export_for_key(self, key, container_name):
        """Get exports for key."""

        class ExportProperties:
            etag = self.export_etag

        class Export:
            name = self.export_file

        if key == self.export_key:
            mock_export = ExportProperties()
        else:
            message = f"No cost report for report name {key} found in container {container_name}."
            raise AzureCostReportNotFound(message)
        return mock_export

    def download_cost_export(self, key, container_name, destination=None):
        """Get exports."""
        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=True, suffix=".csv")
            temp_file.write(b"csvcontents")
            file_path = temp_file.name
        return file_path


class AzureReportDownloaderTest(MasuTestCase):
    """Test Cases for the AzureReportDownloader object."""

    fake = Faker()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService")
    def setUp(self, mock_service):
        """Set up each test."""
        mock_service.return_value = MockAzureService()

        super().setUp()
        self.customer_name = "Azure Customer"
        self.azure_credentials = self.azure_provider.authentication.credentials
        self.azure_data_source = self.azure_provider.billing_source.data_source

        self.downloader = AzureReportDownloader(
            customer_name=self.customer_name,
            auth_credential=self.azure_credentials,
            billing_source=self.azure_data_source,
            provider_uuid=self.azure_provider_uuid,
        )
        self.mock_data = MockAzureService()

    def tearDown(self):
        """Remove created test data."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", return_value=MockAzureService())
    def test_get_azure_client(self, _):
        """Test to verify Azure downloader is initialized."""
        client = self.downloader._get_azure_client(self.azure_credentials, self.azure_data_source)
        self.assertIsNotNone(client)

    def test_get_report_path(self):
        """Test that report path is built correctly."""
        self.assertEqual(self.downloader.directory, self.mock_data.directory)
        self.assertEqual(self.downloader.export_name, self.mock_data.export_name)

        self.assertEqual(self.downloader._get_report_path(self.mock_data.test_date), self.mock_data.report_path)

    def test_get_local_file_for_report(self):
        """Test to get the local file path for a report."""
        expected_local_file = self.mock_data.export_file
        local_file = self.downloader.get_local_file_for_report(self.mock_data.export_key)
        self.assertEqual(expected_local_file, local_file)

    def test_get_manifest(self):
        """Test that Azure manifest is created."""
        expected_start, expected_end = self.mock_data.month_range.split("-")

        manifest = self.downloader._get_manifest(self.mock_data.test_date)
        self.assertEqual(manifest.get("assemblyId"), self.mock_data.export_uuid)
        self.assertEqual(manifest.get("reportKeys"), [self.mock_data.export_file])
        self.assertEqual(manifest.get("Compression"), "PLAIN")
        self.assertEqual(manifest.get("billingPeriod").get("start"), expected_start)
        self.assertEqual(manifest.get("billingPeriod").get("end"), expected_end)

    def test_get_manifest_unexpected_report_name(self):
        """Test that error is thrown when getting manifest with an unexpected report name."""
        with self.assertRaises(AzureReportDownloaderError):
            self.downloader._get_manifest(self.mock_data.bad_test_date)

    def test_download_file(self):
        """Test that Azure report report is downloaded."""
        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.mock_data.container, self.mock_data.export_file
        )
        full_file_path, etag = self.downloader.download_file(self.mock_data.export_key)
        self.assertEqual(full_file_path, expected_full_path)
        self.assertEqual(etag, self.mock_data.export_etag)

    def test_download_missing_file(self):
        """Test that Azure report is not downloaded for incorrect key."""
        key = "badkey"

        with self.assertRaises(AzureReportDownloaderError):
            self.downloader.download_file(key)

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader")
    def test_download_file_matching_etag(self, mock_download_cost_method):
        """Test that Azure report report is not downloaded with matching etag."""
        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.mock_data.container, self.mock_data.export_file
        )
        full_file_path, etag = self.downloader.download_file(self.mock_data.export_key, self.mock_data.export_etag)
        self.assertEqual(full_file_path, expected_full_path)
        self.assertEqual(etag, self.mock_data.export_etag)
        mock_download_cost_method._azure_client.download_cost_export.assert_not_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader")
    @patch("masu.external.downloader.azure.azure_report_downloader.AzureService", return_value=MockAzureService())
    def test_init_with_demo_account(self, mock_download_cost_method, _):
        """Test init with the demo account."""
        account_id = "123456"
        report_name = self.fake.word()
        client_id = self.azure_credentials.get("client_id")
        demo_accounts = {
            account_id: {
                client_id: {
                    "report_name": report_name,
                    "report_prefix": self.fake.word(),
                    "container_name": self.fake.word(),
                }
            }
        }
        with self.settings(DEMO_ACCOUNTS=demo_accounts):
            AzureReportDownloader(
                customer_name=f"acct{account_id}",
                auth_credential=self.azure_credentials,
                billing_source=self.azure_data_source,
                provider_uuid=self.azure_provider_uuid,
            )
            mock_download_cost_method._azure_client.download_cost_export.assert_not_called()

    @patch("masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader._get_manifest")
    def test_get_manifest_context_for_date(self, mock_manifest):
        """Test that the manifest is read."""

        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)

        start_str = current_month.strftime(self.downloader.manifest_date_format)
        assembly_id = "1234"
        compression = UNCOMPRESSED
        report_keys = ["file1", "file2"]
        mock_manifest.return_value = {
            "assemblyId": assembly_id,
            "Compression": compression,
            "reportKeys": report_keys,
            "billingPeriod": {"start": start_str},
        }
        result = self.downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))
