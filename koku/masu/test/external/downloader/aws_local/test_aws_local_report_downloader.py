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
# along with this program.  If not, see <https://www.gnu./licenses/>.
#

"""Test the Local Report Downloader."""
import logging
import os.path
import random
import shutil
import tempfile
from datetime import datetime
from tarfile import TarFile
from unittest.mock import Mock
from unittest.mock import patch

from faker import Faker

from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.external import AWS_REGIONS, PROVIDER_AWS_LOCAL
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
AWS_REGIONS = list(filter(lambda reg: not reg.startswith('cn-'), AWS_REGIONS))
REGION = random.choice(AWS_REGIONS)


class AWSLocalReportDownloaderTest(MasuTestCase):
    """Test Cases for the Local Report Downloader."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up class variables."""
        super().setUpClass()
        cls.fake_customer_name = CUSTOMER_NAME
        cls.fake_report_name = 'koku-local'

        cls.fake_bucket_prefix = PREFIX
        cls.selected_region = REGION
        cls.fake_auth_credential = fake_arn(service='iam', generate_account_id=True)

        cls.manifest_accessor = ReportManifestDBAccessor()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.fake_bucket_name = tempfile.mkdtemp()
        mytar = TarFile.open('./koku/masu/test/data/test_local_bucket.tar.gz')
        mytar.extractall(path=self.fake_bucket_name)
        os.makedirs(DATA_DIR, exist_ok=True)
        self.mock_task = Mock(request=Mock(id=str(self.fake.uuid4()), return_value={}))
        self.report_downloader = ReportDownloader(
            task=self.mock_task,
            customer_name=self.fake_customer_name,
            access_credential=self.fake_auth_credential,
            report_source=self.fake_bucket_name,
            provider_type=PROVIDER_AWS_LOCAL,
            provider_uuid=self.aws_provider_uuid,
        )

        self.aws_local_report_downloader = AWSLocalReportDownloader(
            **{
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': self.fake_bucket_name,
                'provider_uuid': self.aws_provider_uuid,
            }
        )

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        shutil.rmtree(self.fake_bucket_name)

    def test_download_bucket(self):
        """Test to verify that basic report downloading works."""
        test_report_date = datetime(year=2018, month=8, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            self.report_downloader.download_report(test_report_date)
        expected_path = '{}/{}/{}'.format(DATA_DIR, self.fake_customer_name, 'aws-local')
        self.assertTrue(os.path.isdir(expected_path))

    def test_report_name_provided(self):
        """Test initializer when report_name is  provided."""
        report_downloader = AWSLocalReportDownloader(
            **{
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': self.fake_bucket_name,
                'report_name': 'awesome-report',
            }
        )
        self.assertEqual(report_downloader.report_name, 'awesome-report')

    def test_extract_names_no_prefix(self):
        """Test to extract the report and prefix names from a bucket with no prefix."""
        report_downloader = AWSLocalReportDownloader(
            **{
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': self.fake_bucket_name,
            }
        )
        self.assertEqual(report_downloader.report_name, self.fake_report_name)
        self.assertIsNone(report_downloader.report_prefix)

    def test_download_bucket_with_prefix(self):
        """Test to verify that basic report downloading works."""
        fake_bucket = tempfile.mkdtemp()
        mytar = TarFile.open('./koku/masu/test/data/test_local_bucket_prefix.tar.gz')
        mytar.extractall(fake_bucket)
        test_report_date = datetime(year=2018, month=8, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            report_downloader = ReportDownloader(
                self.mock_task,
                self.fake_customer_name,
                self.fake_auth_credential,
                fake_bucket,
                PROVIDER_AWS_LOCAL,
                self.aws_provider_uuid,
            )
            # Names from test report .gz file
            report_downloader.download_report(test_report_date)
        expected_path = '{}/{}/{}'.format(DATA_DIR, self.fake_customer_name, 'aws-local')
        self.assertTrue(os.path.isdir(expected_path))

        shutil.rmtree(fake_bucket)

    def test_extract_names_with_prefix(self):
        """Test to extract the report and prefix names from a bucket with prefix."""
        bucket = tempfile.mkdtemp()
        report_name = 'report-name'
        prefix_name = 'prefix-name'
        full_path = '{}/{}/{}/20180801-20180901/'.format(bucket, prefix_name, report_name)
        os.makedirs(full_path)
        report_downloader = AWSLocalReportDownloader(
            **{
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': bucket,
            }
        )
        self.assertEqual(report_downloader.report_name, report_name)
        self.assertEqual(report_downloader.report_prefix, prefix_name)
        shutil.rmtree(full_path)

    def test_extract_names_with_bad_path(self):
        """Test to extract the report and prefix names from a bad path."""
        bucket = tempfile.mkdtemp()
        report_name = 'report-name'
        prefix_name = 'prefix-name'
        full_path = '{}/{}/{}/20180801-aaaaaaa/'.format(bucket, prefix_name, report_name)
        os.makedirs(full_path)

        report_downloader = AWSLocalReportDownloader(
            **{
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': bucket,
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
                'task': self.mock_task,
                'customer_name': self.fake_customer_name,
                'auth_credential': self.fake_auth_credential,
                'bucket': bucket,
            }
        )
        self.assertIsNone(report_downloader.report_name)
        self.assertIsNone(report_downloader.report_prefix)

        shutil.rmtree(bucket)

    def test_download_missing_month(self):
        """Test to verify that downloading a non-existant month throws proper exception."""
        fake_bucket = tempfile.mkdtemp()
        mytar = TarFile.open('./koku/masu/test/data/test_local_bucket_prefix.tar.gz')
        mytar.extractall(fake_bucket)
        test_report_date = datetime(year=2018, month=7, day=7)
        with patch.object(DateAccessor, 'today', return_value=test_report_date):
            report_downloader = ReportDownloader(
                self.mock_task,
                self.fake_customer_name,
                self.fake_auth_credential,
                fake_bucket,
                PROVIDER_AWS_LOCAL,
                1,
            )
            # Names from test report .gz file
            report_downloader.download_report(test_report_date)
        expected_path = '{}/{}/{}'.format(DATA_DIR, self.fake_customer_name, 'aws-local')
        self.assertFalse(os.path.isdir(expected_path))

    def test_delete_manifest_file_warning(self):
        """Test that an INFO is logged when removing a manifest file that does not exist."""
        with self.assertLogs(logger='masu.external.downloader.aws_local.aws_local_report_downloader',
                             level='INFO') as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.aws_local_report_downloader._remove_manifest_file('None')
            self.assertTrue(captured_logs.output[0].startswith('INFO:'),
                            msg="The log is expected to start with 'INFO:' but instead was: "
                            + captured_logs.output[0])
            self.assertTrue('Could not delete manifest file at' in captured_logs.output[0],
                            msg="""The log message is expected to contain
                                    'Could not delete manifest file at' but instead was: """
                            + captured_logs.output[0])
            # Re-enable log suppression
            logging.disable(logging.CRITICAL)
