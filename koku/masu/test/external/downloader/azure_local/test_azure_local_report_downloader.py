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
# along with this program.  If not, see <https://www.gnu./licenses/>.
#
"""Test the AZURE-Local Report Downloader."""
import datetime
import os.path
import shutil
import tempfile
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase

DATA_DIR = Config.TMP_DIR
FAKE = Faker()
CUSTOMER_NAME = FAKE.word()


class AzureLocalReportDownloaderTest(MasuTestCase):
    """Test Cases for the AZURE-Local Report Downloader."""

    fake = Faker()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.customer_name = "testcustomer"
        self.local_storage = tempfile.mkdtemp()
        self.container_name = "my_container"
        self.directory = "dir"
        self.export_name = "myexport"
        self.date_range = "20190801-20190831"
        self.fake_auth_credential = {
            "credentials": {
                "subscription_id": "2639de71-ca37-4a17-a104-17665a51e7fc",
                "tenant_id": "ae4f8f55-f1a8-4080-9aa8-10779e4113f7",
                "client_id": "d6b607d7-d07a-4ca0-b81d-39631f7323aa",
                "client_secret": "ahhhhh",
            }
        }
        self.fake_bucket_name = {
            "resource_group": {"export_name": self.export_name, "directory": self.directory},
            "storage_account": {"local_dir": self.local_storage, "container": self.container_name},
        }
        test_report = "./koku/masu/test/data/azure/costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv"
        local_dir = "{}/{}/{}/{}/{}".format(
            self.local_storage, self.container_name, self.directory, self.export_name, self.date_range
        )
        os.makedirs(local_dir)
        self.csv_file_name = test_report.split("/")[-1]
        self.csv_key = f"{local_dir}/{self.csv_file_name}"
        shutil.copy2(test_report, self.csv_key)

        os.makedirs(DATA_DIR, exist_ok=True)

        self.report_downloader = ReportDownloader(
            customer_name=self.customer_name,
            access_credential=self.fake_auth_credential,
            report_source=self.fake_bucket_name,
            provider_type=Provider.PROVIDER_AZURE_LOCAL,
            provider_uuid=self.azure_provider_uuid,
        )

        self.azure_local_report_downloader = AzureLocalReportDownloader(
            **{
                "customer_name": self.customer_name,
                "auth_credential": self.fake_auth_credential,
                "billing_source": self.fake_bucket_name,
                "bucket": self.fake_bucket_name,
                "provider_uuid": self.azure_provider_uuid,
            }
        )

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        shutil.rmtree(self.local_storage)

    def test_initializer(self):
        """Test the Azure-Local initializer."""
        self.assertIsNotNone(self.report_downloader)

    def test_download_file(self):
        """Test Azure-Local report download."""
        expected_full_path = "{}/{}/azure/{}/{}".format(
            Config.TMP_DIR, self.customer_name.replace(" ", "_"), self.container_name, self.csv_file_name
        )
        full_file_path, etag = self.azure_local_report_downloader.download_file(self.csv_key)
        self.assertEqual(full_file_path, expected_full_path)
        self.assertIsNotNone(etag)

        # Download a second time, verify etag is returned
        full_file_path, second_run_etag = self.azure_local_report_downloader.download_file(self.csv_key)
        self.assertEqual(etag, second_run_etag)
        self.assertEqual(full_file_path, expected_full_path)

    def test_download_report(self):
        """Test the top level Azure-Local download_report."""
        test_report_date = datetime.datetime(year=2019, month=8, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            report_context = {
                "date": test_report_date.date(),
                "manifest_id": 1,
                "comporession": "GZIP",
                "current_file": "./koku/masu/test/data/azure/costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv",
            }
            self.report_downloader.download_report(report_context)
            expected_path = "{}/{}/{}".format(DATA_DIR, self.customer_name, "azure")
            self.assertTrue(os.path.isdir(expected_path))
