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
from datetime import datetime
from masu.external.downloader.azure.azure_report_downloader import AzureReportDownloader
from masu.test import MasuTestCase

from unittest.mock import patch



class MockAzureService:

    def describe_cost_management_exports(self):
        return [{"name": "export_name", "container": "test_container", "directory": "cost"}]

    def get_latest_cost_export_for_date(self, date_range, container_name):
        class Export:
            name = 'costreport_0505541d-8fc3-4134-b972-631dc8f20b0b.csv'
        mock_export = Export()
        return mock_export

    def get_cost_export_for_key(self, key, container_name):
        return None

    def download_cost_export(self, key, container_name, destination=None):
        return None

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
            billing_source=self.billing_source)

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

    def test_get_manifest(self):
        """Test that Azure manifest is created."""
        test_date = datetime(2019, 8, 15)
        manifest = self.downloader._get_manifest(test_date)
        self.assertEqual(manifest.get('assemblyId'), '0505541d-8fc3-4134-b972-631dc8f20b0b')
        self.assertEqual(manifest.get('reportKeys'), ['costreport_0505541d-8fc3-4134-b972-631dc8f20b0b.csv'])
        self.assertEqual(manifest.get('Compression'), 'PLAIN')
        self.assertEqual(manifest.get('billingPeriod').get('start'), '20190801')
        self.assertEqual(manifest.get('billingPeriod').get('end'), '20190831')

    def test_get_report_context_for_date(self):
        """Test that report context is retrieved for date."""
        pass

    def test_prepare_db_manifest_record(self):
        """Test that manifest db record is preped."""
        pass

    def test_download_file(self):
        """Test that Azure report id downloaded."""
        pass
