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
"""Test the Report Downloader."""
import logging
import os.path
import shutil
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

from faker import Faker

from api.models import Provider
from masu.config import Config
from masu.external.date_accessor import DateAccessor
from masu.external.downloader.ocp.ocp_report_downloader import OCPReportDownloader
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase

DATA_DIR = Config.TMP_DIR
REPORTS_DIR = Config.INSIGHTS_LOCAL_REPORT_DIR

FAKE = Faker()
CUSTOMER_NAME = FAKE.word()


class OCPReportDownloaderTest(MasuTestCase):
    """Test Cases for the OCP Report Downloader."""

    fake = Faker()

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.fake_customer_name = CUSTOMER_NAME
        self.fake_report_name = "ocp-report"
        self.cluster_id = "my-ocp-cluster-1"

        report_path = "{}/{}/{}".format(REPORTS_DIR, self.cluster_id, "20180901-20181001")
        os.makedirs(report_path, exist_ok=True)

        test_file_path = (
            "./koku/masu/test/data/ocp/e6b3701e-1e91" "-433b-b238-a31e49937558_February-2019-my-ocp-cluster-1.csv"
        )
        self.test_file_path = os.path.join(report_path, os.path.basename(test_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_file_path))

        test_storage_file_path = "./koku/masu/test/data/ocp/e6b3701e-1e91" "-433b-b238-a31e49937558_storage.csv"
        self.test_storage_file_path = os.path.join(report_path, os.path.basename(test_storage_file_path))
        shutil.copyfile(test_file_path, os.path.join(report_path, self.test_storage_file_path))

        test_manifest_path = "./koku/masu/test/data/ocp/manifest.json"
        self.test_manifest_path = os.path.join(report_path, os.path.basename(test_manifest_path))
        shutil.copyfile(test_manifest_path, os.path.join(report_path, self.test_manifest_path))

        self.mock_task = Mock(request=Mock(id=str(self.fake.uuid4()), return_value={}))
        self.report_downloader = ReportDownloader(
            task=self.mock_task,
            customer_name=self.fake_customer_name,
            access_credential=self.cluster_id,
            report_source=None,
            provider_type=Provider.PROVIDER_OCP,
            provider_uuid=self.ocp_provider_uuid,
            cache_key=self.fake.word(),
        )

        self.ocp_report_downloader = OCPReportDownloader(
            **{
                "task": self.mock_task,
                "customer_name": self.fake_customer_name,
                "auth_credential": self.cluster_id,
                "bucket": None,
                "provider_uuid": self.ocp_provider_uuid,
                "cache_key": self.fake.word(),
            }
        )

    def tearDown(self):
        """Remove created test data."""
        super().tearDown()
        shutil.rmtree(REPORTS_DIR, ignore_errors=True)

    @patch("masu.util.aws.common.copy_data_to_s3_bucket", return_value=None)
    def test_download_bucket(self, mock_copys3):
        """Test to verify that basic report downloading works."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            self.report_downloader.download_report(test_report_date)
        expected_path = "{}/{}/{}".format(Config.TMP_DIR, self.fake_customer_name, "ocp")
        self.assertTrue(os.path.isdir(expected_path))

    def test_download_bucket_no_csv_found(self):
        """Test to verify that basic report downloading with no .csv file in source directory."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            os.remove(self.test_file_path)
            os.remove(self.test_storage_file_path)
            with self.assertRaises(FileNotFoundError):
                self.report_downloader.download_report(test_report_date)

    def test_download_bucket_non_csv_found(self):
        """Test to verify that basic report downloading with non .csv file in source directory."""
        test_report_date = datetime(year=2018, month=9, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            # Remove .csv
            os.remove(self.test_file_path)
            os.remove(self.test_storage_file_path)

            # Create .txt file
            txt_file_path = "{}/{}".format(os.path.dirname(self.test_file_path), "report.txt")
            open(txt_file_path, "a").close()
            with self.assertRaises(FileNotFoundError):
                self.report_downloader.download_report(test_report_date)

    def test_download_bucket_source_directory_missing(self):
        """Test to verify that basic report downloading when source directory doesn't exist."""
        reports = []
        # Set current date to a day that is outside of the test file's date range.
        test_report_date = datetime(year=2018, month=10, day=7)
        with patch.object(DateAccessor, "today", return_value=test_report_date):
            reports = self.report_downloader.download_report(test_report_date)
        self.assertEqual(reports, [])

    def test_remove_manifest_file(self):
        """Test that a manifest file is deleted after use."""
        test_report_date = datetime(year=2018, month=9, day=7)
        self.assertTrue(os.path.isfile(self.test_manifest_path))
        self.ocp_report_downloader._remove_manifest_file(test_report_date)
        self.assertFalse(os.path.isfile(self.test_manifest_path))

    def test_delete_manifest_file_warning(self):
        """Test that an INFO is logged when removing a manifest file that does not exist."""
        with self.assertLogs(
            logger="masu.external.downloader.ocp.ocp_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.ocp_report_downloader._remove_manifest_file(datetime.now())
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
