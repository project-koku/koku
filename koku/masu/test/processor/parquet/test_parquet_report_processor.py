#
# Copyright 2020 Red Hat, Inc.
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
import logging
import os
import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import faker
from botocore.exceptions import ClientError
from django.test import override_settings

from api.models import Provider
from api.utils import DateHelper
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.test import MasuTestCase
from masu.util.aws.common import aws_post_processor
from masu.util.common import get_column_converters


class TestParquetReportProcessor(MasuTestCase):
    """Test cases for Parquet Report Processor."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        # cls.fake_reports = [
        #     {"file": cls.fake.word(), "compression": "GZIP"},
        #     {"file": cls.fake.word(), "compression": "PLAIN"},
        # ]

        # cls.fake_account = fake_arn(service="iam", generate_account_id=True)
        cls.fake_uuid = "d4703b6e-cd1f-4253-bfd4-32bdeaf24f97"
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.request_id = 1
        self.account_id = self.schema[4:]
        self.manifest_id = 1
        self.report_name = "koku-1.csv.gz"
        self.report_path = f"/my/{self.test_assembly_id}/{self.report_name}"
        self.report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            compression="GZIP",
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "create_table": True},
        )

    @patch("masu.processor.parquet.parquet_report_processor.ReportManifestDBAccessor")
    def test_convert_to_parquet(self, mock_manifest_accessor):
        """Test the convert_to_parquet task."""
        logging.disable(logging.NOTSET)
        expected_logs = [
            "missing required argument: request_id",
            "missing required argument: account",
            "missing required argument: provider_uuid",
        ]
        with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
            with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
                self.report_processor.convert_to_parquet(None, None, None, None, "start_date", "manifest_id", [])
                for expected in expected_logs:
                    self.assertIn(expected, " ".join(logger.output))

        expected = "Skipping convert_to_parquet. Parquet processing is disabled."
        with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
            self.report_processor.convert_to_parquet(
                "request_id", "account", "provider_uuid", "provider_type", "start_date", "manifest_id", "csv_file"
            )
            self.assertIn(expected, " ".join(logger.output))

        expected = "Parquet processing is enabled, but no start_date was given for processing."
        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                self.report_processor.convert_to_parquet(
                    "request_id", "account", "provider_uuid", "provider_type", None, "manifest_id", "csv_file"
                )
                self.assertIn(expected, " ".join(logger.output))

        expected = "Parquet processing is enabled, but the start_date was not a valid date string ISO 8601 format."
        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                self.report_processor.convert_to_parquet(
                    "request_id", "account", "provider_uuid", "provider_type", "bad_date", "manifest_id", "csv_file"
                )
                self.assertIn(expected, " ".join(logger.output))

        expected = "Could not establish report type"
        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                self.report_processor.convert_to_parquet(
                    "request_id", "account", "provider_uuid", "OCP", "2020-01-01T12:00:00", "manifest_id", "csv_file"
                )
                self.assertIn(expected, " ".join(logger.output))

        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    (
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                        "get_file_keys_from_s3_with_manifest_id"
                    ),
                    return_value=["cur.csv.gz"],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.remove_files_not_in_set_from_s3_bucket"
                    ):
                        with patch(
                            "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                            "convert_csv_to_parquet"
                        ):
                            self.report_processor.convert_to_parquet(
                                "request_id",
                                "account",
                                "provider_uuid",
                                "AWS",
                                "2020-01-01T12:00:00",
                                "manifest_id",
                                "csv_file",
                            )

        expected = "Failed to convert the following files to parquet"
        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    (
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                        "get_file_keys_from_s3_with_manifest_id"
                    ),
                    return_value=["cost_export.csv"],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet",
                        return_value=False,
                    ):
                        with self.assertLogs(
                            "masu.processor.parquet.parquet_report_processor", level="INFO"
                        ) as logger:
                            self.report_processor.convert_to_parquet(
                                "request_id",
                                "account",
                                "provider_uuid",
                                "provider_type",
                                "2020-01-01T12:00:00",
                                "manifest_id",
                                "csv_file",
                            )
                            self.assertIn(expected, " ".join(logger.output))

        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    (
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                        "get_file_keys_from_s3_with_manifest_id"
                    ),
                    return_value=["storage_usage.csv"],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet"
                    ):
                        self.report_processor.convert_to_parquet(
                            "request_id",
                            "account",
                            "provider_uuid",
                            "OCP",
                            "2020-01-01T12:00:00",
                            "manifest_id",
                            "csv_file",
                        )

        with patch("masu.processor.parquet.parquet_report_processor.enable_trino_processing", return_value=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix"):
                with patch(
                    (
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                        "get_file_keys_from_s3_with_manifest_id"
                    ),
                    return_value=[],
                ):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet"
                    ):
                        self.report_processor.convert_to_parquet(
                            "request_id", "account", "provider_uuid", "OCP", "2020-01-01T12:00:00", "manifest_id"
                        )

    def test_get_file_keys_from_s3_with_manifest_id(self):
        """Test get_file_keys_from_s3_with_manifest_id."""
        files = self.report_processor.get_file_keys_from_s3_with_manifest_id("request_id", "s3_path", "manifest_id")
        self.assertEqual(files, [])

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_PARQUET_PROCESSING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource") as mock_s3:
                files = self.report_processor.get_file_keys_from_s3_with_manifest_id("request_id", None, "manifest_id")
                self.assertEqual(files, [])

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_PARQUET_PROCESSING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource") as mock_s3:
                mock_s3.side_effect = ClientError({}, "Error")
                files = self.report_processor.get_file_keys_from_s3_with_manifest_id(
                    "request_id", "s3_path", "manifest_id"
                )
                self.assertEqual(files, [])

    @override_settings(ENABLE_PARQUET_PROCESSING=True)
    def test_convert_csv_to_parquet(self):
        """Test convert_csv_to_parquet."""
        result = self.report_processor.convert_csv_to_parquet(
            "request_id", None, "s3_parquet_path", "local_path", "manifest_id", "csv_filename"
        )
        self.assertFalse(result)

        result = self.report_processor.convert_csv_to_parquet(
            "request_id", "s3_csv_path", "s3_parquet_path", "local_path", "manifest_id", "csv_filename"
        )
        self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource") as mock_s3:
                with patch("masu.processor.parquet.parquet_report_processor.Path"):
                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                        mock_os.path.split.return_value = ("path", "file.csv")
                        mock_s3.side_effect = ClientError({}, "Error")
                        result = self.report_processor.convert_csv_to_parquet(
                            "request_id",
                            "s3_csv_path",
                            "s3_parquet_path",
                            "local_path",
                            "manifest_id",
                            "csv_filename.csv",
                        )
                        self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource"):
                with patch("masu.processor.parquet.parquet_report_processor.Path"):
                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                        mock_os.path.split.return_value = ("path", "file.csv.gz")
                        result = self.report_processor.convert_csv_to_parquet(
                            "request_id",
                            "s3_csv_path",
                            "s3_parquet_path",
                            "local_path",
                            "manifest_id",
                            "csv_filename.csv.gz",
                        )
                        self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource"):
                with patch("masu.processor.parquet.parquet_report_processor.Path"):
                    with patch("masu.processor.parquet.parquet_report_processor.pd") as mock_pd:
                        with patch("masu.processor.parquet.parquet_report_processor.open") as mock_open:
                            with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                                mock_os.path.split.return_value = ("path", "file.csv.gz")
                                mock_pd.read_csv.return_value.__enter__.return_value = [1, 2, 3]
                                mock_open.side_effect = ValueError()
                                result = self.report_processor.convert_csv_to_parquet(
                                    "request_id",
                                    "s3_csv_path",
                                    "s3_parquet_path",
                                    "local_path",
                                    "manifest_id",
                                    "csv_filename.csv.gz",
                                )
                                self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource"):
                with patch("masu.processor.parquet.parquet_report_processor.Path"):
                    with patch("masu.processor.parquet.parquet_report_processor.pd"):
                        with patch("masu.processor.parquet.parquet_report_processor.open"):
                            with patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"):
                                with patch(
                                    "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                                    "create_parquet_table"
                                ):
                                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                                        mock_os.path.split.return_value = ("path", "file.csv.gz")
                                        result = self.report_processor.convert_csv_to_parquet(
                                            "request_id",
                                            "s3_csv_path",
                                            "s3_parquet_path",
                                            "local_path",
                                            "manifest_id",
                                            "csv_filename.csv.gz",
                                        )
                                        self.assertTrue(result)

        with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource"):
            with patch("masu.processor.parquet.parquet_report_processor.Path"):
                with patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"):
                    with patch(
                        "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                        "create_parquet_table"
                    ):
                        with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                            mock_os.path.split.return_value = ("path", "file.csv")
                            test_report_test_path = "./koku/masu/test/data/test_cur.csv.gz"
                            temp_dir = tempfile.mkdtemp()
                            test_report = f"{temp_dir}/test_cur.csv.gz"
                            shutil.copy2(test_report_test_path, test_report)
                            local_path = "/tmp/parquet"
                            Path(local_path).mkdir(parents=True, exist_ok=True)
                            converters = get_column_converters(Provider.PROVIDER_AWS)

                            result = self.report_processor.convert_csv_to_parquet(
                                "request_id",
                                "s3_csv_path",
                                "s3_parquet_path",
                                local_path,
                                "manifest_id",
                                test_report,
                                converters=converters,
                                post_processor=aws_post_processor,
                                report_type=Provider.PROVIDER_AWS,
                            )
                            self.assertTrue(result)
                            shutil.rmtree(local_path, ignore_errors=True)
                            shutil.rmtree(temp_dir)

    def test_convert_csv_to_parquet_report_type_already_processed(self):
        """Test that we don't re-create a table when we already have created this run."""
        with patch("masu.processor.parquet.parquet_report_processor.settings", ENABLE_S3_ARCHIVING=True):
            with patch("masu.processor.parquet.parquet_report_processor.get_s3_resource"):
                with patch("masu.processor.parquet.parquet_report_processor.Path"):
                    with patch("masu.processor.parquet.parquet_report_processor.pd"):
                        with patch("masu.processor.parquet.parquet_report_processor.open"):
                            with patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"):
                                with patch(
                                    "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                                    "create_parquet_table"
                                ) as mock_create_table:
                                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                                        mock_os.path.split.return_value = ("path", "file.csv")
                                        self.report_processor.presto_table_exists["report_type"] = True
                                        result = self.report_processor.convert_csv_to_parquet(
                                            "request_id",
                                            "s3_csv_path",
                                            "s3_parquet_path",
                                            "local_path",
                                            "manifest_id",
                                            "csv_filename.csv.gz",
                                            report_type="report_type",
                                        )
                                        self.assertTrue(result)
                                        mock_create_table.assert_not_called()

    @patch.object(ReportParquetProcessorBase, "sync_hive_partitions")
    @patch.object(ReportParquetProcessorBase, "get_or_create_postgres_partition")
    @patch.object(ReportParquetProcessorBase, "table_exists")
    @patch.object(ReportParquetProcessorBase, "schema_exists")
    @patch.object(ReportParquetProcessorBase, "create_schema")
    @patch.object(ReportParquetProcessorBase, "create_table")
    def test_create_parquet_table(
        self, mock_create_table, mock_create_schema, mock_schema_exists, mock_table_exists, mock_partition, mock_sync
    ):
        """Test create_parquet_table function."""
        test_matrix = [
            {
                "provider_uuid": str(self.aws_provider_uuid),
                "expected_create": True,
                "patch": (AWSReportParquetProcessor, "create_bill"),
            },
            {
                "provider_uuid": str(self.ocp_provider_uuid),
                "expected_create": True,
                "patch": (OCPReportParquetProcessor, "create_bill"),
            },
            {
                "provider_uuid": str(self.azure_provider_uuid),
                "expected_create": True,
                "patch": (AzureReportParquetProcessor, "create_bill"),
            },
            {
                "provider_uuid": str(uuid.uuid4()),
                "expected_create": False,
                "patch": (AWSReportParquetProcessor, "create_bill"),
            },
        ]
        account = 10001
        manifest_id = "1"
        s3_parquet_path = "data/to/parquet"
        output_file = "local_path/file.parquet"
        report_type = "pod_usage"

        mock_schema_exists.return_value = False
        mock_table_exists.return_value = False

        for test in test_matrix:
            provider_uuid = test.get("provider_uuid")
            patch_class, patch_method = test.get("patch")
            with patch.object(patch_class, patch_method) as mock_create_bill:
                self.report_processor.create_parquet_table(
                    account, provider_uuid, manifest_id, s3_parquet_path, output_file, report_type
                )
                if test.get("expected_create"):
                    mock_schema_exists.assert_called()
                    mock_table_exists.assert_called()
                    mock_create_schema.assert_called()
                    mock_create_table.assert_called()
                    mock_create_bill.assert_called()
                    mock_partition.assert_called()
                    mock_sync.assert_called()
                else:
                    mock_schema_exists.assert_not_called()
                    mock_table_exists.assert_not_called()
                    mock_create_schema.assert_not_called()
                    mock_create_table.assert_not_called()
                    mock_create_bill.assert_not_called()
                    mock_partition.assert_not_called()
                    mock_sync.assert_not_called()
            mock_schema_exists.reset_mock()
            mock_table_exists.reset_mock()
            mock_create_schema.reset_mock()
            mock_create_table.reset_mock()
            mock_partition.reset_mock()
            mock_sync.reset_mock()

    @patch.object(ReportParquetProcessorBase, "sync_hive_partitions")
    @patch.object(AWSReportParquetProcessor, "create_bill")
    @patch.object(ReportParquetProcessorBase, "get_or_create_postgres_partition")
    @patch.object(ReportParquetProcessorBase, "table_exists")
    @patch.object(ReportParquetProcessorBase, "schema_exists")
    @patch.object(ReportParquetProcessorBase, "create_schema")
    @patch.object(ReportParquetProcessorBase, "create_table")
    def test_create_parquet_table_table_exists(
        self,
        mock_create_table,
        mock_create_schema,
        mock_schema_exists,
        mock_table_exists,
        mock_partition,
        mock_create_bill,
        mock_sync,
    ):
        """Test create_parquet_table function."""

        account = 10001
        provider_uuid = self.aws_provider_uuid
        manifest_id = "1"
        s3_parquet_path = "data/to/parquet"
        output_file = "local_path/file.parquet"
        report_type = "pod_usage"

        mock_schema_exists.return_value = True
        mock_table_exists.return_value = True

        self.report_processor.create_parquet_table(
            account, provider_uuid, manifest_id, s3_parquet_path, output_file, report_type
        )

        mock_schema_exists.assert_called()
        mock_table_exists.assert_called()
        mock_create_schema.assert_not_called()
        mock_create_table.assert_not_called()
        mock_create_bill.assert_called()
        mock_partition.assert_called()
        mock_sync.assert_called()

    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_to_parquet")
    def test_process(self, mock_convert):
        """Test that the process method starts parquet conversion."""
        self.report_processor.process()
        mock_convert.assert_called_with(
            self.request_id,
            self.account_id,
            self.aws_provider_uuid,
            Provider.PROVIDER_AWS,
            str(DateHelper().today.date()),
            self.manifest_id,
            [self.report_path],
        )
        mock_convert.reset_mock()

        file_list = ["path/to/file_one", "path/to/file_two", "path/to/file_three"]
        ocp_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=f"/my/{self.test_assembly_id}/{self.report_name}",
            compression="GZIP",
            provider_uuid=self.ocp_provider_uuid,
            provider_type=Provider.PROVIDER_OCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "split_files": file_list},
        )
        ocp_processor.process()
        mock_convert.assert_called_with(
            self.request_id,
            self.account_id,
            self.ocp_provider_uuid,
            Provider.PROVIDER_OCP,
            str(DateHelper().today.date()),
            self.manifest_id,
            file_list,
        )

    @patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket")
    @patch("masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.create_parquet_table")
    def test_process_gcp(self, mock_create_table, mock_s3_copy):
        """Test the processor for GCP."""

        report_path = "/tmp/original_csv.csv"
        with open(report_path, "w") as f:
            f.write("one,two,three")
        self.assertTrue(os.path.exists(report_path))

        file_list = ["/tmp/file_one.csv", "/tmp/file_two.csv", "/tmp/file_three.csv"]
        for path in file_list:
            with open(path, "w") as f:
                f.write("one,two,three")
            self.assertTrue(os.path.exists(path))

        gcp_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=report_path,
            compression="GZIP",
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP,
            manifest_id=self.manifest_id,
            context={"request_id": self.request_id, "start_date": DateHelper().today, "split_files": file_list},
        )

        with patch(
            "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_to_parquet"
        ) as mock_convert:
            gcp_processor.process()
            mock_convert.assert_called_with(
                self.request_id,
                self.account_id,
                self.gcp_provider_uuid,
                Provider.PROVIDER_GCP,
                str(DateHelper().today.date()),
                self.manifest_id,
                file_list,
            )

        gcp_processor.process()

        self.assertFalse(os.path.exists(report_path))
        for path in file_list:
            self.assertFalse(os.path.exists(report_path))
