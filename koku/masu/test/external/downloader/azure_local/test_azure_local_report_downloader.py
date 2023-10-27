#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AZURE-Local Report Downloader."""
import datetime
import os.path
import shutil
import tempfile
from unittest.mock import patch

from faker import Faker
from model_bakery import baker

from api.models import Provider
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.azure_local.azure_local_report_downloader import AzureLocalReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase
from reporting_common.models import CostUsageReportStatus

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
            credentials=self.fake_auth_credential,
            data_source=self.fake_bucket_name,
            provider_type=Provider.PROVIDER_AZURE_LOCAL,
            provider_uuid=self.azure_provider_uuid,
        )

        self.azure_local_report_downloader = AzureLocalReportDownloader(
            **{
                "customer_name": self.customer_name,
                "credentials": self.fake_auth_credential,
                "data_source": self.fake_bucket_name,
                "bucket": self.fake_bucket_name,  # TODO: bucket?
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

    @patch("masu.util.aws.common.copy_data_to_s3_bucket")
    def test_download_report(self, *args):
        """Test the top level Azure-Local download_report."""
        test_report_date = datetime.datetime(year=2019, month=8, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            filename = "costreport_a243c6f2-199f-4074-9a2c-40e671cf1584.csv"
            manifest_id = 1
            report_context = {
                "date": test_report_date,
                "manifest_id": manifest_id,
                "comporession": "GZIP",
                "current_file": f"./koku/masu/test/data/azure/{filename}",
            }
            baker.make(CostUsageReportStatus, manifest_id=manifest_id, report_name=filename)

            with patch("masu.external.downloader.azure.azure_report_downloader.open"):
                with patch(
                    "masu.external.downloader.azure_local.azure_local_report_downloader.create_daily_archives",
                    return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
                ):
                    self.report_downloader.download_report(report_context)
                    expected_path = "{}/{}/{}".format(DATA_DIR, self.customer_name, "azure")
                    self.assertTrue(os.path.isdir(expected_path))

    def test_get_manifest(self):
        """Test _get_manifest method."""
        mock_datetime = datetime.datetime(day=2, month=8, year=2019)

        manifest_json, _ = self.azure_local_report_downloader._get_manifest(mock_datetime)

        self.assertTrue("assemblyId" in manifest_json.keys())
        self.assertTrue("billingPeriod" in manifest_json.keys())
        self.assertTrue("reportKeys" in manifest_json.keys())
        self.assertTrue("reportKeys" in manifest_json.keys())
        self.assertTrue("Compression" in manifest_json.keys())
