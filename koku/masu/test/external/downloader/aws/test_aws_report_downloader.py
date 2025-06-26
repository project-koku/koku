#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the AWS S3 utility functions."""
import copy
import io
import logging
import os.path
import random
import shutil
import tempfile
from unittest.mock import Mock
from unittest.mock import patch

from botocore.exceptions import ClientError
from faker import Faker
from model_bakery import baker

from api.models import Provider
from masu.config import Config
from masu.database.report_manifest_db_accessor import ReportManifestDBAccessor
from masu.exceptions import MasuProviderError
from masu.external import AWS_REGIONS
from masu.external import UNCOMPRESSED
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloader
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderError
from masu.external.downloader.aws.aws_report_downloader import AWSReportDownloaderNoFileError
from masu.external.downloader.aws.aws_report_downloader import create_daily_archives
from masu.external.downloader.aws.aws_report_downloader import get_processing_date
from masu.external.report_downloader import ReportDownloader
from masu.test import MasuTestCase
from masu.test.external.downloader.aws import fake_arn
from masu.util.aws import common as utils
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus

DATA_DIR = Config.TMP_DIR
FAKE = Faker()
CUSTOMER_NAME = FAKE.word()
REPORT = FAKE.word()
BUCKET = FAKE.word()
PREFIX = FAKE.word()

# the cn endpoints aren't supported by moto, so filter them out
AWS_REGIONS = list(filter(lambda reg: not reg.startswith("cn-"), AWS_REGIONS))
REGION = random.choice(AWS_REGIONS)


def mock_kwargs_error(**kwargs):
    """Mock side effect method for raising an AWSReportDownloaderError."""
    raise AWSReportDownloaderError()


def mock_download_file_error(manifest):
    """Mock side effect for raising an AWSReportDownloaderNoFileError."""
    raise AWSReportDownloaderNoFileError()


class FakeSession:
    """
    Fake Boto Session object.

    This is here because Moto doesn't mock out the 'cur' endpoint yet. As soon
    as Moto supports 'cur', this can be removed.
    """

    @staticmethod
    def client(service, region_name=None):
        """Return a fake AWS Client with a report."""
        fake_report = {
            "ReportDefinitions": [
                {
                    "ReportName": REPORT,
                    "TimeUnit": random.choice(["HOURLY", "DAILY"]),
                    "Format": random.choice(["text", "csv"]),
                    "Compression": random.choice(["ZIP", "GZIP"]),
                    "S3Bucket": BUCKET,
                    "S3Prefix": PREFIX,
                    "S3Region": region_name or REGION,
                }
            ]
        }

        if "cur" in service:
            return Mock(**{"describe_report_definitions.return_value": fake_report})
        else:
            return Mock()


class FakeSessionNoReport:
    """
    Fake Boto Session object with no reports in the S3 bucket.

    This is here because Moto doesn't mock out the 'cur' endpoint yet. As soon
    as Moto supports 'cur', this can be removed.
    """

    @staticmethod
    def client(service, region_name=None):
        """Return a fake AWS Client with no report."""
        fake_report = {"ReportDefinitions": []}

        # only mock the 'cur' boto client.
        if "cur" in service:
            return Mock(**{"describe_report_definitions.return_value": fake_report})
        else:
            return Mock()


class FakeSessionDownloadError:
    """
    Fake Boto Session object.

    This is here because Moto doesn't mock out the 'cur' endpoint yet. As soon
    as Moto supports 'cur', this can be removed.
    """

    @staticmethod
    def client(service, region_name=None):
        """Return a fake AWS Client with an error."""
        fake_report = {
            "ReportDefinitions": [
                {
                    "ReportName": REPORT,
                    "TimeUnit": random.choice(["HOURLY", "DAILY"]),
                    "Format": random.choice(["text", "csv"]),
                    "Compression": random.choice(["ZIP", "GZIP"]),
                    "S3Bucket": BUCKET,
                    "S3Prefix": PREFIX,
                    "S3Region": region_name or REGION,
                }
            ]
        }

        if "cur" in service:
            return Mock(**{"describe_report_definitions.return_value": fake_report})
        elif "s3" in service:
            return Mock(**{"get_object.side_effect": mock_kwargs_error})
        else:
            return Mock()


class AWSReportDownloaderTest(MasuTestCase):
    """Test Cases for the AWS S3 functions."""

    fake = Faker()

    @classmethod
    def setUpClass(cls):
        """Set up shared class variables."""
        super().setUpClass()
        cls.fake_customer_name = CUSTOMER_NAME
        cls.fake_report_name = REPORT
        cls.fake_bucket_prefix = PREFIX
        cls.fake_bucket_name = BUCKET
        cls.selected_region = REGION
        cls.auth_credential = fake_arn(service="iam", generate_account_id=True)

        cls.manifest_accessor = ReportManifestDBAccessor()

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def setUp(self, fake_session):
        """Set up shared variables."""
        super().setUp()
        os.makedirs(DATA_DIR, exist_ok=True)

        self.credentials = {"role_arn": self.auth_credential}
        self.data_source = {"bucket": self.fake_bucket_name}
        self.storage_only_data_source = {"bucket": self.fake_bucket_name, "storage_only": True}
        self.ingress_reports = [f"{self.fake_bucket_name}/test_report_file.csv"]

        self.report_downloader = ReportDownloader(
            customer_name=self.fake_customer_name,
            credentials=self.credentials,
            data_source=self.data_source,
            provider_type=Provider.PROVIDER_AWS,
            provider_uuid=self.aws_provider_uuid,
        )
        self.aws_report_downloader = AWSReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.data_source,
                "report_name": self.fake_report_name,
                "provider_uuid": self.aws_provider_uuid,
            }
        )
        self.aws_storage_only_report_downloader = AWSReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.storage_only_data_source,
                "report_name": self.fake_report_name,
                "provider_uuid": self.aws_provider_uuid,
            }
        )
        self.aws_ingress_report_downloader = AWSReportDownloader(
            **{
                "customer_name": self.fake_customer_name,
                "credentials": self.credentials,
                "data_source": self.storage_only_data_source,
                "report_name": self.fake_report_name,
                "provider_uuid": self.aws_provider_uuid,
                "ingress_reports": self.ingress_reports,
            }
        )
        self.aws_manifest = CostUsageReportManifest.objects.filter(provider_id=self.aws_provider_uuid).first()
        self.aws_manifest_id = self.aws_manifest.id

    def tearDown(self):
        """Remove test generated data."""
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch("masu.external.downloader.aws.aws_report_downloader.create_daily_archives")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._check_size")
    @patch("masu.external.downloader.aws.aws_report_downloader.utils.remove_files_not_in_set_from_s3_bucket")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_file(self, fake_session, mock_remove, mock_check_size, mock_daily_archives):
        """Test the download file method."""
        mock_check_size.return_value = True
        mock_daily_archives.return_value = [], {}
        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        with patch("masu.external.downloader.aws.aws_report_downloader.pd.read_csv"):
            downloader.download_file(self.fake.file_path(), manifest_id=1)
            mock_check_size.assert_called()

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._check_size")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_ingress_report_file(self, fake_session, mock_check_size):
        """Test the download file method."""
        mock_check_size.return_value = True
        customer_name = self.fake_customer_name
        expected_full_path = "{}/{}/aws/{}".format(
            Config.TMP_DIR, customer_name.replace(" ", "_"), self.ingress_reports[0]
        )
        downloader = AWSReportDownloader(
            customer_name,
            self.credentials,
            self.storage_only_data_source,
            ingress_reports=self.ingress_reports,
        )
        with patch("masu.external.downloader.aws.aws_report_downloader.open"):
            with patch(
                "masu.external.downloader.aws.aws_report_downloader.create_daily_archives",
                return_value=[["file_one", "file_two"], {"start": "", "end": ""}],
            ):
                full_file_path, etag, _, __, ___ = downloader.download_file(self.ingress_reports[0])
                self.assertEqual(full_file_path, expected_full_path)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSessionDownloadError)
    def test_download_report_missing_bucket(self, fake_session):
        """Test download fails when bucket is missing."""
        fake_session.return_value.__enter__ = Mock()
        fake_report_date = self.fake.date_time().replace(day=1)
        fake_report_date_str = fake_report_date.strftime("%Y%m%dT000000.000Z")
        manifest_id = 1
        expected_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        input_key = f"/koku/20180701-20180801/{expected_assembly_id}/koku-1.csv.gz"
        mock_manifest = {
            "assemblyId": expected_assembly_id,
            "billingPeriod": {"start": fake_report_date_str},
            "reportKeys": [input_key],
        }
        baker.make(CostUsageReportStatus, manifest_id=manifest_id, report_name="file")

        with patch.object(AWSReportDownloader, "_get_manifest", return_value=("", mock_manifest)):
            with self.assertRaises(AWSReportDownloaderError):
                report_downloader = ReportDownloader(
                    customer_name=self.fake_customer_name,
                    credentials=self.credentials,
                    data_source=self.data_source,
                    provider_type=Provider.PROVIDER_AWS,
                    provider_uuid=self.aws_provider_uuid,
                )
                report_context = {
                    "date": fake_report_date.date(),
                    "manifest_id": manifest_id,
                    "comporession": "GZIP",
                    "current_file": "/my/file",
                }
                report_downloader.download_report(report_context)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_missing_report_name(self, fake_session):
        """Test downloading a report with an invalid report name."""
        with self.assertRaises(MasuProviderError):
            AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source, "wrongreport")

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_default_report(self, fake_session):
        """Test assume aws role works."""
        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        self.assertEqual(downloader.report_name, self.fake_report_name)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_initial_storage_only_download(self, fake_session):
        """Test assume aws role works with storage only source."""
        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.storage_only_data_source)
        self.assertEqual(downloader.report, "")

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSessionNoReport)
    def test_download_default_report_no_report_found(self, fake_session):
        """Test download fails when no reports are found."""
        with self.assertRaises(MasuProviderError):
            AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)

    @patch("masu.external.downloader.aws.aws_report_downloader.shutil")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_success(self, fake_session, fake_shutil):
        """Test _check_size is successful."""
        fake_client = Mock()
        fake_client.get_object.return_value = {"ContentLength": 123456, "Body": Mock()}
        fake_shutil.disk_usage.return_value = (10, 10, 4096 * 1024 * 1024)

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension=random.choice(["json", "csv.gz"]))
        result = downloader._check_size(fakekey, check_inflate=False)
        self.assertTrue(result)

    @patch("masu.external.downloader.aws.aws_report_downloader.shutil")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_fail_nospace(self, fake_session, fake_shutil):
        """Test _check_size fails if there is no more space."""
        fake_client = Mock()
        fake_client.get_object.return_value = {"ContentLength": 123456, "Body": Mock()}
        fake_shutil.disk_usage.return_value = (10, 10, 10)

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension=random.choice(["json", "csv.gz"]))
        result = downloader._check_size(fakekey, check_inflate=False)
        self.assertFalse(result)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_fail_nosize(self, fake_session):
        """Test _check_size fails if there report has no size."""
        fake_client = Mock()
        fake_client.get_object.return_value = {}

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension=random.choice(["json", "csv.gz"]))
        with self.assertRaises(AWSReportDownloaderError):
            downloader._check_size(fakekey, check_inflate=False)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_fail_access_denied(self, fake_session):
        """Test _check_size fails if there report has no size."""
        fake_response = {"Error": {"Code": "AccessDenied"}}
        fake_client = Mock()
        fake_client.get_object.side_effect = ClientError(fake_response, "masu-test")

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension=random.choice(["json", "csv.gz"]))
        with self.assertRaises(AWSReportDownloaderNoFileError):
            downloader._check_size(fakekey, check_inflate=False)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_fail_unknown_error(self, fake_session):
        """Test _check_size fails if there report has no size."""
        fake_response = {"Error": {"Code": "Unknown"}}
        fake_client = Mock()
        fake_client.get_object.side_effect = ClientError(fake_response, "masu-test")

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension=random.choice(["json", "csv.gz"]))
        with self.assertRaises(AWSReportDownloaderError):
            downloader._check_size(fakekey, check_inflate=False)

    @patch("masu.external.downloader.aws.aws_report_downloader.shutil")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_inflate_success(self, fake_session, fake_shutil):
        """Test _check_size inflation succeeds."""
        fake_client = Mock()
        fake_client.get_object.return_value = {"ContentLength": 123456, "Body": io.BytesIO(b"\xd2\x02\x96I")}
        fake_shutil.disk_usage.return_value = (10, 10, 4096 * 1024 * 1024)

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension="csv.gz")
        result = downloader._check_size(fakekey, check_inflate=True)
        self.assertTrue(result)

    @patch("masu.external.downloader.aws.aws_report_downloader.shutil")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_check_size_inflate_fail(self, fake_session, fake_shutil):
        """Test _check_size fails when inflation fails."""
        fake_client = Mock()
        fake_client.get_object.return_value = {"ContentLength": 123456, "Body": io.BytesIO(b"\xd2\x02\x96I")}
        fake_shutil.disk_usage.return_value = (10, 10, 1234567)

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension="csv.gz")
        result = downloader._check_size(fakekey, check_inflate=True)
        self.assertFalse(result)

    @patch("masu.external.downloader.aws.aws_report_downloader.shutil")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_file_check_size_fail(self, fake_session, fake_shutil):
        """Test _check_size fails when key is fake."""
        fake_client = Mock()
        fake_client.get_object.return_value = {"ContentLength": 123456, "Body": io.BytesIO(b"\xd2\x02\x96I")}
        fake_shutil.disk_usage.return_value = (10, 10, 1234567)

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        fakekey = self.fake.file_path(depth=random.randint(1, 5), extension="csv.gz")
        with self.assertRaises(AWSReportDownloaderError):
            downloader.download_file(fakekey)

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_file_raise_downloader_err(self, fake_session):
        """Test _check_size fails when there is a downloader error."""
        fake_response = {"Error": {"Code": self.fake.word()}}
        fake_client = Mock()
        fake_client.get_object.side_effect = ClientError(fake_response, "masu-test")

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        with self.assertRaises(AWSReportDownloaderError):
            downloader.download_file(self.fake.file_path())

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_file_raise_nofile_err(self, fake_session):
        """Test that downloading a nonexistent file fails with AWSReportDownloaderNoFileError."""
        fake_response = {"Error": {"Code": "NoSuchKey"}}
        fake_client = Mock()
        fake_client.get_object.side_effect = ClientError(fake_response, "masu-test")

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        with self.assertRaises(AWSReportDownloaderNoFileError):
            downloader.download_file(self.fake.file_path())

    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_download_file_raise_access_denied_err(self, fake_session):
        """Test that downloading a fails when accessdenied occurs."""
        fake_response = {"Error": {"Code": "AccessDenied"}}
        fake_client = Mock()
        fake_client.get_object.side_effect = ClientError(fake_response, "masu-test")

        downloader = AWSReportDownloader(self.fake_customer_name, self.credentials, self.data_source)
        downloader.s3_client = fake_client

        with self.assertRaises(AWSReportDownloaderNoFileError):
            downloader.download_file(self.fake.file_path())

    def test_remove_manifest_file(self):
        """Test that we remove the manifest file."""
        manifest_file = f"{DATA_DIR}/test_manifest.json"

        with open(manifest_file, "w") as f:
            f.write("Test")

        self.assertTrue(os.path.isfile(manifest_file))
        self.aws_report_downloader._remove_manifest_file(manifest_file)
        self.assertFalse(os.path.isfile(manifest_file))

    def test_delete_manifest_file_warning(self):
        """Test that an INFO is logged when removing a manifest file that does not exist."""
        with self.assertLogs(
            logger="masu.external.downloader.aws.aws_report_downloader", level="INFO"
        ) as captured_logs:
            # Disable log suppression
            logging.disable(logging.NOTSET)
            self.aws_report_downloader._remove_manifest_file("None")
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

    def test_init_with_demo_account(self):
        """Test init with the demo account."""
        mock_task = Mock(request=Mock(id=str(self.fake.uuid4()), return_value={}))
        account_id = "123456"
        arn = fake_arn(service="iam", generate_account_id=True)
        credentials = {"role_arn": arn}
        report_name = FAKE.word()
        demo_accounts = {account_id: {arn: {"report_name": report_name, "report_prefix": FAKE.word()}}}
        with self.settings(DEMO_ACCOUNTS=demo_accounts):
            with patch("masu.util.aws.common.get_assume_role_session") as mock_session:
                AWSReportDownloader(
                    **{
                        "task": mock_task,
                        "customer_name": f"acct{account_id}",
                        "credentials": credentials,
                        "data_source": {"bucket": FAKE.word()},
                        "report_name": report_name,
                        "provider_uuid": self.aws_provider_uuid,
                    }
                )
                mock_session.assert_called_once()

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._remove_manifest_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._get_manifest")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_manifest_context_for_date(self, mock_session, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = self.dh.this_month_start
        downloader = AWSReportDownloader(
            self.fake_customer_name, self.credentials, self.data_source, provider_uuid=self.aws_provider_uuid
        )

        start_str = current_month.strftime(downloader.manifest_date_format)
        assembly_id = "1234"
        compression = downloader.report.get("Compression")
        report_keys = ["file1", "file2"]
        mock_manifest.return_value = (
            "",
            {
                "assemblyId": assembly_id,
                "Compression": compression,
                "reportKeys": report_keys,
                "billingPeriod": {"start": start_str},
            },
            self.dh.now,
        )

        result = downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("assembly_id"), assembly_id)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._remove_manifest_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._get_manifest")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_pseudo_manifest_context_for_date(self, mock_session, mock_manifest, mock_delete):
        """Test that the pseudo manifest is created and read."""
        current_month = self.dh.this_month_start
        downloader = AWSReportDownloader(
            self.fake_customer_name,
            self.credentials,
            self.storage_only_data_source,
            provider_uuid=self.aws_provider_uuid,
            ingress_reports=self.ingress_reports,
        )

        start_str = current_month.strftime(downloader.manifest_date_format)
        assembly_id = "1234"
        compression = "PLAIN"
        mock_manifest.return_value = (
            "",
            {
                "assemblyId": assembly_id,
                "Compression": compression,
                "start_date": start_str,
                "filenames": self.ingress_reports,
            },
            self.dh.now,
        )

        result = downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result.get("compression"), compression)
        self.assertIsNotNone(result.get("files"))

    def test_get_storage_only_manifest_file(self):
        """Test _get_manifest method w storage only."""
        mock_datetime = self.dh.now

        result = self.aws_storage_only_report_downloader.get_manifest_context_for_date(mock_datetime)
        self.assertEqual(result, {})

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._remove_manifest_file")
    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._get_manifest")
    @patch("masu.util.aws.common.get_assume_role_session", return_value=FakeSession)
    def test_get_manifest_context_for_date_no_manifest(self, mock_session, mock_manifest, mock_delete):
        """Test that the manifest is read."""
        current_month = self.dh.this_month_start
        downloader = AWSReportDownloader(
            self.fake_customer_name, self.credentials, self.data_source, provider_uuid=self.aws_provider_uuid
        )

        mock_manifest.return_value = ("", {"reportKeys": []}, self.dh.now)

        result = downloader.get_manifest_context_for_date(current_month)
        self.assertEqual(result, {})

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.download_file")
    def test_get_manifest(self, mock_download_file):
        """Test _get_manifest method."""
        mock_datetime = self.dh.now
        mock_file_name = "testfile"
        mock_download_file.return_value = (mock_file_name, None, mock_datetime, [], {})
        fake_manifest_dict = {"foo": "bar"}
        with patch("masu.external.downloader.aws.aws_report_downloader.open"):
            with patch(
                "masu.external.downloader.aws.aws_report_downloader.json.load", return_value=fake_manifest_dict
            ):
                manifest_file, manifest_json, manifest_modified_timestamp = self.aws_report_downloader._get_manifest(
                    mock_datetime
                )
                self.assertEqual(manifest_file, mock_file_name)
                self.assertEqual(manifest_json, fake_manifest_dict)
                self.assertEqual(manifest_modified_timestamp, mock_datetime)

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader.download_file")
    def test_get_manifest_file_not_found(self, mock_download_file):
        """Test _get_manifest method when file is not found."""
        mock_datetime = self.dh.now
        mock_download_file.side_effect = AWSReportDownloaderNoFileError("fake error")

        manifest_file, manifest_json, manifest_modified_timestamp = self.aws_report_downloader._get_manifest(
            mock_datetime
        )
        self.assertEqual(manifest_file, "")
        self.assertEqual(manifest_json, self.aws_report_downloader.empty_manifest)
        self.assertIsNone(manifest_modified_timestamp)

    @patch("masu.external.downloader.aws.aws_report_downloader.AWSReportDownloader._generate_monthly_pseudo_manifest")
    def test_generate_pseudo_manifest(self, mock_pseudo_manifest):
        """Test Generating pseudo manifest for storage only."""
        mock_datetime = self.dh.now
        expected_manifest_data = {
            "assembly_id": "1234",
            "compression": UNCOMPRESSED,
            "start_date": mock_datetime,
            "file_names": self.ingress_reports,
        }
        mock_pseudo_manifest.return_value = expected_manifest_data

        result_manifest = self.aws_ingress_report_downloader._generate_monthly_pseudo_manifest(mock_datetime)
        self.assertEqual(result_manifest, expected_manifest_data)

    def test_get_processing_date(self):
        """Test getting dataframe with date for processing."""
        file_name = "2023-06-01-not-final.csv"
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_interval = "identity/TimeInterval"
        expected_cols = copy.deepcopy(utils.RECOMMENDED_COLUMNS) | copy.deepcopy(utils.OPTIONAL_COLS)
        expected_cols |= {"costCategory/qe_source", "costCategory/name", "costCategory/cost_env"}
        start_date = self.dh.this_month_start.replace(year=2023, month=6, tzinfo=None)
        end_date = self.dh.this_month_start.replace(year=2023, month=6, day=2, tzinfo=None)
        expected_date = self.dh.this_month_start.replace(year=2023, month=6, day=1, tzinfo=None)
        with patch(
            "masu.external.downloader.aws.aws_report_downloader.check_provider_setup_complete", return_Value=True
        ):
            with patch("masu.util.aws.common.get_or_clear_daily_s3_by_date", return_value=expected_date):
                with patch(
                    "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.get_manifest_daily_start_date",
                    return_value=expected_date,
                ):
                    use_cols, time_interval, process_date = get_processing_date(
                        temp_path, None, 1, self.aws_provider_uuid, start_date, end_date, None, "tracing_id"
                    )
                    self.assertEqual(use_cols, expected_cols)
                    self.assertEqual(time_interval, expected_interval)
                    self.assertEqual(process_date, expected_date)
                    os.remove(temp_path)

    @patch("masu.util.aws.common.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives(self, mock_copy):
        """Test that we correctly create daily archive files."""
        file = "2023-06-01"
        file_name = f"{file}.csv"
        manifest_id = self.aws_manifest_id
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = [
            f"{temp_dir}/2023-06-01_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
        ]
        start_date = self.dh.this_month_start.replace(year=2023, month=6).date()
        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            daily_file_names, date_range = create_daily_archives(
                "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
            )
            expected_date_range = {"start": "2023-06-01", "end": "2023-06-01", "invoice_month": None}
            mock_copy.assert_called()
            self.assertEqual(date_range, expected_date_range)
            self.assertIsInstance(daily_file_names, list)
            self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))
            for daily_file in expected_daily_files:
                self.assertTrue(os.path.exists(daily_file))
                os.remove(daily_file)
            os.remove(temp_path)

    @patch("masu.util.aws.common.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_check_leading_zeros(self, mock_copy):
        """Check that the leading zeros are kept when downloading."""
        file = "2023-06-01"
        file_name = f"{file}.csv"
        manifest_id = self.aws_manifest_id
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2023, month=6).date()

        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            daily_file_names, date_range = create_daily_archives(
                "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
            )

        for daily_file in daily_file_names:
            with open(daily_file) as file:
                csv = file.readlines()

            self.assertIn("0099999999999", csv[1].split(","))
            os.remove(daily_file)

        os.remove(temp_path)

    def test_create_daily_archives_dates_out_of_range(self):
        """Test that we correctly create daily archive files."""
        file = "2023-06-01"
        file_name = f"{file}.csv"
        manifest_id = self.aws_manifest_id
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)

        start_date = self.dh.this_month_start.replace(year=2023, month=9, tzinfo=None)
        daily_file_names, date_range = create_daily_archives(
            "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
        )
        self.assertEqual(date_range, {})
        self.assertEqual(daily_file_names, [])

    def test_create_daily_archives_empty_frame(self):
        """Test that we correctly create daily archive files."""
        file = "empty_frame"
        file_name = f"{file}.csv"
        manifest_id = self.aws_manifest_id
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        start_date = self.dh.this_month_start.replace(year=2023, month=6, tzinfo=None)
        daily_file_names, date_range = create_daily_archives(
            "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
        )
        self.assertEqual(date_range, {})
        self.assertIsInstance(daily_file_names, list)
        self.assertEqual(daily_file_names, [])

    @patch("masu.util.aws.common.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives_alt_columns(self, mock_copy):
        """Test that we correctly create daily archive files with alt columns."""
        file = "2022-07-01-alt-columns"
        file_name = f"{file}.csv"
        manifest_id = self.aws_manifest_id
        file_path = f"./koku/masu/test/data/aws/{file_name}"
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, file_name)
        shutil.copy2(file_path, temp_path)
        expected_daily_files = [
            f"{temp_dir}/2022-07-01_manifestid-{manifest_id}_basefile-{file}_batch-0.csv",
        ]
        start_date = self.dh.this_month_start.replace(year=2022, month=7).date()
        with patch(
            "masu.database.report_manifest_db_accessor.ReportManifestDBAccessor.set_manifest_daily_start_date",
            return_value=start_date,
        ):
            daily_file_names, date_range = create_daily_archives(
                "trace_id", "account", self.aws_provider_uuid, temp_path, file_name, manifest_id, start_date, None
            )
            expected_date_range = {"start": "2022-07-01", "end": "2022-07-01", "invoice_month": None}
            mock_copy.assert_called()
            self.assertEqual(date_range, expected_date_range)
            self.assertIsInstance(daily_file_names, list)
            self.assertEqual(sorted(daily_file_names), sorted(expected_daily_files))
            for daily_file in expected_daily_files:
                self.assertTrue(os.path.exists(daily_file))
                os.remove(daily_file)
            os.remove(temp_path)
