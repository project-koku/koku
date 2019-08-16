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

from masu.config import Config

from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader, AzureReportDownloaderError
from masu.external.downloader.azure.azure_service import AzureCostReportNotFound
from masu.external.downloader.report_downloader_base import ReportDownloaderBase

from masu.test import MasuTestCase

from unittest.mock import patch

DATA_DIR = Config.TMP_DIR

class MockAzureService:

    def describe_cost_management_exports(self):
        return [{"name": "export_name", "container": "test_container", "directory": "cost"}]

    def get_latest_cost_export_for_path(self, report_path, container_name):
        class Export:
            name = 'costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
        if report_path == 'cost/export_name/20190801-20190831':
            mock_export = Export()
        else:
            message = f'No cost report found in container {container_name} for '\
                      f'path {report_path}.'
            raise AzureCostReportNotFound(message)
        return mock_export

    def get_cost_export_for_key(self, key, container_name):

        class ExportProperties:
            etag = "absdfwef"

        class Export:
            name = 'costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
            properties = ExportProperties()
        if key == 'cost/costreport/20190801-20190831/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv':
            mock_export = Export()
        else:
            message = f'No cost report for report name {key} found in container {container_name}.'
            raise AzureCostReportNotFound(message)
        return mock_export

    def download_cost_export(self, key, container_name, destination=None):
        file_path = destination
        if not destination:
            temp_file = NamedTemporaryFile(delete=True, suffix='.csv')
            temp_file.write(b'csvcontents')
            file_path = temp_file.name
        return file_path


class AzureReportDownloaderTest(MasuTestCase):
    """Test Cases for the AzureReportDownloader object."""

    @patch('masu.external.downloader.azure.azure_report_downloader.AzureService')
    def setUp(self, mock_service):
        """Set up each test."""
        mock_service.return_value = MockAzureService()

        super().setUp()
        self.customer_name = "Azure Customer"
        self.auth_credential = self.azure_credentials
        self.billing_source = self.azure_data_source

        self.downloader = AzureReportDownloader(
            customer_name=self.customer_name,
            auth_credential=self.auth_credential,
            billing_source=self.billing_source,
            provider_id=self.azure_provider_id)

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch('masu.external.downloader.azure.azure_report_downloader.AzureService', return_value=MockAzureService())
    def test_get_azure_client(self, mock_service):
        """Test to verify Azure downloader is initialized."""
        client = self.downloader._get_azure_client(self.azure_credentials, self.azure_data_source)
        self.assertIsNotNone(client)

    def test_get_report_path(self):
        """Test that report path is built correctly."""
        test_date = datetime(2019, 8, 15)
        self.assertEqual(self.downloader.directory, 'cost')
        self.assertEqual(self.downloader.export_name, 'export_name')

        self.assertEqual(self.downloader._get_report_path(test_date), 'cost/export_name/20190801-20190831')

    def test_get_local_file_for_report(self):
        """Test to get the local file path for a report."""
        key = 'cost/costreport/20190801-20190831/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
        expected_local_file = 'costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
        local_file = self.downloader.get_local_file_for_report(key)
        self.assertEqual(expected_local_file, local_file)

    def test_get_manifest(self):
        """Test that Azure manifest is created."""
        test_date = datetime(2019, 8, 15)
        manifest = self.downloader._get_manifest(test_date)
        self.assertEqual(manifest.get('assemblyId'), '9c308505-61d3-487c-a1bb-017956c9170a')
        self.assertEqual(manifest.get('reportKeys'), ['costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'])
        self.assertEqual(manifest.get('Compression'), 'PLAIN')
        self.assertEqual(manifest.get('billingPeriod').get('start'), '20190801')
        self.assertEqual(manifest.get('billingPeriod').get('end'), '20190831')

    def test_get_report_context_for_date_should_download(self):
        """Test that report context is retrieved for date."""
        test_date = datetime(2019, 8, 15)
        with patch.object(ReportDownloaderBase, 'check_if_manifest_should_be_downloaded', return_value=True):
            manifest = self.downloader.get_report_context_for_date(test_date)
        self.assertEqual(manifest.get('assembly_id'), '9c308505-61d3-487c-a1bb-017956c9170a')
        self.assertEqual(manifest.get('compression'), 'PLAIN')
        self.assertEqual(manifest.get('files'), ['costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'])
        self.assertIsNotNone(manifest.get('manifest_id'))

    def test_get_report_context_for_date_should_not_download(self):
        """Test that report context is not retrieved when download check fails."""
        test_date = datetime(2019, 8, 15)
        with patch.object(ReportDownloaderBase, 'check_if_manifest_should_be_downloaded', return_value=False):
            manifest = self.downloader.get_report_context_for_date(test_date)
        self.assertEqual(manifest, {})

    def test_get_report_context_for_incorrect_date(self):
        """Test that report context is not retrieved with an unexpected date."""
        test_date = datetime(2019, 9, 15)
        with patch.object(ReportDownloaderBase, 'check_if_manifest_should_be_downloaded', return_value=False):
            manifest = self.downloader.get_report_context_for_date(test_date)
        self.assertEqual(manifest, {})

    def test_download_file(self):
        """Test that Azure report report is downloaded."""
        key = 'cost/costreport/20190801-20190831/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
        full_file_path, etag = self.downloader.download_file(key)
        self.assertEqual(full_file_path, '/var/tmp/masu/Azure_Customer/azure/test_container/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv')
        self.assertEqual(etag, 'absdfwef')

    def test_download_missing_file(self):
        """Test that Azure report is not downloaded for incorrect key."""
        key = 'badkey'

        with self.assertRaises(AzureReportDownloaderError):
            self.downloader.download_file(key)

    @patch('masu.external.downloader.azure.azure_report_downloader.AzureReportDownloader')
    def test_download_file_matching_etag(self, mock_download_cost_method):
        """Test that Azure report report is not downloaded with matching etag."""
        key = 'cost/costreport/20190801-20190831/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv'
        etag = 'absdfwef'
        full_file_path, etag = self.downloader.download_file(key, etag)
        self.assertEqual(full_file_path, '/var/tmp/masu/Azure_Customer/azure/test_container/costreport_9c308505-61d3-487c-a1bb-017956c9170a.csv')
        self.assertEqual(etag, 'absdfwef')
        mock_download_cost_method._azure_client.download_cost_export.assert_not_called()
