#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Local Report Downloader."""
import logging
import os.path
import random
import shutil
import tempfile
from datetime import datetime
from tarfile import TarFile
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import AWS_REGIONS
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.aws_local.aws_local_report_downloader import AWSLocalReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn

DATA_DIR = Config.TMP_DIR
FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
REPORT = FAKE.word()
PREFIX = FAKE.word()

# the cn endpoints aren't supported by moto, so filter them out
AWS_REGIONS = list(filter(lambda reg: not reg.startswith("cn-"), AWS_REGIONS))
REGION = random.choice(AWS_REGIONS)


class AWSLocalReportDownloaderTest(MasuTestCase):
    """Test Cases for the Local Report Downloader."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up class variables."""
        super().setUpClass()
        cls.fake_customer_name = CUSTOMER_NAME
        cls.fake_report_name = "koku-local"

        cls.fake_bucket_prefix = PREFIX
        cls.selected_region = REGION
        cls.fake_auth_credential = fake_arn(service="iam", generate_account_id=True)

        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.fake_bucket_name = tempfile.mkdtemp()
        mytar = TarFile.open("./koku/masu/test/data/test_local_bucket.tar.gz")
        mytar.extractall(path=self.fake_bucket_name)
        os.makedirs(DATA_DIR, exist_ok=True)

        self.credentials = {"role_arn": self.fake_auth_credential}
        self.data_source = {"bucket": self.fake_bucket_name}

        self.report_downloader = ReportDownloader(
            customer_name=self.fake_customer_name,
            credentials=self.credentials,
            data_source=self.data_source,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            provider_uuid=self.aws_provider_uuid,
        )

        self.aws_local_report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
                "provider_uuid": self.aws_provider_uuid,
            }
        )

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        shutil.rmtree(self.fake_bucket_name)

    def test_download_bucket(self):
        """Test to verify that basic report downloading works."""
        test_report_date = datetime(year=2018, month=8, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            report_context = {
                "date": test_report_date.date(),
                "manifest_id": 1,
                "comporession": "GZIP",
                "current_file": "./koku/masu/test/data/test_local_bucket.tar.gz",
            }
            self.report_downloader.download_report(report_context)
        expected_path = "{}/{}/{}".format(DATA_DIR, self.fake_customer_name, "aws-local")
        self.assertTrue(os.path.isdir(expected_path))

    def test_report_name_provided(self):
        """Test initializer when report_name is  provided."""
        report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
                "report_name": "awesome-report",
            }
        )
        self.assertEqual(report_downloader.report_name, "awesome-report")

    def test_extract_names_no_prefix(self):
        """Test to extract the report and prefix names from a bucket with no prefix."""
        report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
            }
        )
        self.assertEqual(report_downloader.report_name, self.fake_report_name)
        self.assertIsNone(report_downloader.report_prefix)

    def test_download_bucket_with_prefix(self):
        """Test to verify that basic report downloading works."""
        fake_bucket = tempfile.mkdtemp()
        mytar = TarFile.open("./koku/masu/test/data/test_local_bucket_prefix.tar.gz")
        mytar.extractall(fake_bucket)
        test_report_date = datetime(year=2018, month=8, day=7)
        fake_data_source = {"bucket": fake_bucket}
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            report_downloader = ReportDownloader(
                self.fake_customer_name,
                self.credentials,
                fake_data_source,
                Provider.PROVIDER_AWS_LOCAL,
                self.aws_provider_uuid,
            )
            # Names from test report .gz file
            report_context = {
                "date": test_report_date.date(),
                "manifest_id": 1,
                "comporession": "GZIP",
                "current_file": "./koku/masu/test/data/test_local_bucket.tar.gz",
            }
            report_downloader.download_report(report_context)
        expected_path = "{}/{}/{}".format(DATA_DIR, self.fake_customer_name, "aws-local")
        self.assertTrue(os.path.isdir(expected_path))

        shutil.rmtree(fake_bucket)

    def test_extract_names_with_prefix(self):
        """Test to extract the report and prefix names from a bucket with prefix."""
        bucket = tempfile.mkdtemp()
        report_name = "report-name"
        prefix_name = "prefix-name"
        full_path = f"{bucket}/{prefix_name}/{report_name}/20180801-20180901/"
        os.makedirs(full_path)
        report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": {"bucket": bucket},
            }
        )
        self.assertEqual(report_downloader.report_name, report_name)
        self.assertEqual(report_downloader.report_prefix, prefix_name)
        shutil.rmtree(full_path)

    def test_extract_names_with_bad_path(self):
        """Test to extract the report and prefix names from a bad path."""
        bucket = tempfile.mkdtemp()
        report_name = "report-name"
        prefix_name = "prefix-name"
        full_path = f"{bucket}/{prefix_name}/{report_name}/20180801-aaaaaaa/"
        os.makedirs(full_path)

        report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": {"bucket": bucket},
            }
        )
        self.assertIsNone(report_downloader.report_name)
        self.assertIsNone(report_downloader.report_prefix)

        shutil.rmtree(full_path)

    def test_extract_names_with_incomplete_path(self):
        """Test to extract the report and prefix from a path where a CUR hasn't been generated yet."""
        bucket = tempfile.mkdtemp()
        report_downloader = AWSLocalReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": {"bucket": bucket},
            }
        )
        self.assertIsNone(report_downloader.report_name)
        self.assertIsNone(report_downloader.report_prefix)

        shutil.rmtree(bucket)

    def test_delete_manifest_file_warning(self):
        """Test that an INFO is logged when removing a manifest file that does not exist."""
        with self.assertLogs(
            logger="masu.external.downloader.aws_local.aws_local_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.aws_local_report_downloader._remove_manifest_file("None")
            self.assertTrue(
                captured_logs.output[0].startswith("INFO:"),
                msg="The log is expected to start with 'INFO:' but instead was: " + captured_logs.output[0],
            )
            self.assertTrue(
                "Could not delete manifest file at" in captured_logs.output[0],
                msg="""The log message is expected to contain
                                    'Could not delete manifest file at' but instead was: """
                + captured_logs.output[0],
            )
            # Re-enable log suppression
            logging.disable(logging.CRITICAL)

    @patch(
        "masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader._remove_manifest_file"
    )
    @patch("masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader._get_manifest")
    def test_get_manifest_context_for_date(self, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)
        downloader = AWSLocalReportDownloader(
            self.fake_customer_name, self.credentials, self.data_source, provider_uuid=self.aws_provider_uuid
        )

        start_str = current_month.strftime(downloader.manifest_date_format)
        assembly_id = "1234"
        compression = "GZIP"
        report_keys = ["file1", "file2"]
        mock_manifest.return_value = (
            "",
            {
                "assemblyId": assembly_id,
                "Compression": compression,
                "reportKeys": report_keys,
                "billingPeriod": {"start": start_str},
            },
            DateAccessor().today(),
        )

        result = downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

    @patch(
        "masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader._remove_manifest_file"
    )
    @patch("masu.external.downloader.aws_local.aws_local_report_downloader.AWSLocalReportDownloader._get_manifest")
    def test_get_manifest_context_for_date_no_manifest(self, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = DateAccessor().today().replace(day=1, second=1, microsecond=1)
        downloader = AWSLocalReportDownloader(
            self.fake_customer_name, self.credentials, self.data_source, provider_uuid=self.aws_provider_uuid
        )

        mock_manifest.return_value = ("", {"reportKeys": []}, DateAccessor().today())

        result = downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result, {})
