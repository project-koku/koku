#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import datetime
import logging
import os
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from unittest.mock import PropertyMock

import faker
import pandas as pd
from django_tenants.utils import schema_context

from api.models import Provider
from api.utils import DateHelper
from masu.config import Config
from masu.database.ingress_report_db_accessor import IngressReportDBAccessor
from masu.processor.aws.aws_report_parquet_processor import AWSReportParquetProcessor
from masu.processor.azure.azure_report_parquet_processor import AzureReportParquetProcessor
from masu.processor.gcp.gcp_report_parquet_processor import GCPReportParquetProcessor
from masu.processor.oci.oci_report_parquet_processor import OCIReportParquetProcessor
from masu.processor.ocp.ocp_report_parquet_processor import OCPReportParquetProcessor
from masu.processor.parquet.parquet_report_processor import CSV_EXT
from masu.processor.parquet.parquet_report_processor import CSV_GZIP_EXT
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessor
from masu.processor.parquet.parquet_report_processor import ParquetReportProcessorError
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.test import MasuTestCase
from masu.util.aws.aws_post_processor import AWSPostProcessor
from masu.util.azure.azure_post_processor import AzurePostProcessor
from masu.util.gcp.gcp_post_processor import GCPPostProcessor
from masu.util.oci.oci_post_processor import OCIPostProcessor
from masu.util.ocp.ocp_post_processor import OCPPostProcessor


class TestParquetReportProcessor(MasuTestCase):
    """Test cases for Parquet Report Processor."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.fake = faker.Faker()
        cls.fake_uuid = "d4703b6e-cd1f-4253-bfd4-32bdeaf24f97"
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def setUp(self):
        """Set up shared test variables."""
        super().setUp()
        self.test_assembly_id = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.test_etag = "fake_etag"
        self.tracing_id = 1
        self.account_id = self.schema[4:]
        self.manifest_id = 1
        self.start_date = DateHelper().today
        self.report_name = "koku-1.csv.gz"
        self.report_path = f"/my/{self.test_assembly_id}/{self.report_name}"
        self.report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
        )
        ingress_uuid = "882083b7-ea62-4aab-aa6a-f0d08d65ee2b"
        self.ingress_report_dict = {
            "uuid": ingress_uuid,
            "created_timestamp": DateHelper().today,
            "completed_timestamp": None,
            "reports_list": ["test"],
            "source": self.aws_provider,
        }
        self.ingress_report_accessor = IngressReportDBAccessor(self.schema)
        with schema_context(self.schema):
            self.added_ingress_report = self.ingress_report_accessor.add(**self.ingress_report_dict)
        self.report_processor_ingress = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS,
            manifest_id=self.manifest_id,
            ingress_reports=["test.csv"],
            ingress_reports_uuid=ingress_uuid,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
        )

    def test_tracing_id(self):
        """Test that the tracing_id property is handled."""
        self.assertIsNotNone(self.report_processor.tracing_id)

        # Test with missing context
        with self.assertRaises(ParquetReportProcessorError):
            report_processor = ParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={},
            )
            report_processor.tracing_id

    def test_start_date(self):
        """Test that the start_date property is handled."""
        self.assertIsInstance(self.report_processor.start_date, datetime.date)

        report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"start_date": "2021-04-22"},
        )
        self.assertIsInstance(report_processor.start_date, datetime.date)

        report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"start_date": datetime.datetime.utcnow()},
        )
        self.assertIsInstance(report_processor.start_date, datetime.date)

        with self.assertRaises(ParquetReportProcessorError):
            report_processor = ParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={},
            )
            report_processor.start_date

    def test_file_extension(self):
        """Test that the file_extension property is handled."""
        self.assertEqual(self.report_processor.file_extension, CSV_GZIP_EXT)

        report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path="file.csv",
            provider_uuid=self.aws_provider_uuid,
            provider_type=Provider.PROVIDER_AWS_LOCAL,
            manifest_id=self.manifest_id,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
        )
        self.assertEqual(report_processor.file_extension, CSV_EXT)

        with self.assertRaises(ParquetReportProcessorError):
            report_processor = ParquetReportProcessor(
                schema_name=self.schema,
                report_path="file.xlsx",
                provider_uuid=self.aws_provider_uuid,
                provider_type=Provider.PROVIDER_AWS_LOCAL,
                manifest_id=self.manifest_id,
                context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
            )
            report_processor.file_extension

    def test_post_processor(self):
        """Test that the post_processor property is handled."""
        test_matrix = [
            {
                "provider_uuid": str(self.aws_provider_uuid),
                "provider_type": Provider.PROVIDER_AWS,
                "expected": AWSPostProcessor,
            },
            {
                "provider_uuid": str(self.azure_provider_uuid),
                "provider_type": Provider.PROVIDER_AZURE,
                "expected": AzurePostProcessor,
            },
            {
                "provider_uuid": str(self.gcp_provider_uuid),
                "provider_type": Provider.PROVIDER_GCP,
                "expected": GCPPostProcessor,
            },
            {
                "provider_uuid": str(self.oci_provider_uuid),
                "provider_type": Provider.PROVIDER_OCI,
                "expected": OCIPostProcessor,
            },
            {
                "provider_uuid": str(self.ocp_provider_uuid),
                "provider_type": Provider.PROVIDER_OCP,
                "expected": OCPPostProcessor,
            },
        ]

        for test in test_matrix:
            report_processor = ParquetReportProcessor(
                schema_name=self.schema,
                report_path=self.report_path,
                provider_uuid=test.get("provider_uuid"),
                provider_type=test.get("provider_type"),
                manifest_id=self.manifest_id,
                context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
            )
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.report_type",
                return_value="pod_usage",
            ):
                self.assertIsInstance(report_processor._set_post_processor(), test.get("expected"))

    @patch("masu.processor.parquet.parquet_report_processor.os.path.exists")
    @patch("masu.processor.parquet.parquet_report_processor.os.remove")
    def test_convert_to_parquet_validation_error(self, mock_remove, mock_exists):
        """Test the convert_to_parquet task hits column validation error."""
        with patch("masu.processor.parquet.parquet_report_processor.Path"):
            with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                mock_os.path.split.return_value = ("path", "file.csv.gz")
                with patch("masu.processor.parquet.parquet_report_processor.pd.read_csv") as mock_cols:
                    mock_cols.columns.return_value = {"columns"}
                    _, __, result = self.report_processor_ingress.convert_csv_to_parquet("csv_filename.csv.gz")
                    self.assertFalse(result)

    def test_unknown_provider_post_processor(self):
        """Test that nothing is returned"""
        report_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=self.report_path,
            provider_uuid="123456",
            provider_type="unknown_provider",
            manifest_id=self.manifest_id,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
        )
        dataframe, daily, success = report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
        self.assertIsNone(dataframe)
        self.assertIsNone(daily)
        self.assertFalse(success)

    @patch("masu.processor.parquet.parquet_report_processor.os.path.exists")
    @patch("masu.processor.parquet.parquet_report_processor.os.remove")
    def test_convert_to_parquet(self, mock_remove, mock_exists):
        """Test the convert_to_parquet task."""
        logging.disable(logging.NOTSET)

        with patch.object(ParquetReportProcessor, "csv_path_s3", new_callable=PropertyMock) as mock_csv_path:
            mock_csv_path.return_value = None
            file_name, data_frame = self.report_processor.convert_to_parquet()
            self.assertEqual(file_name, "")
            self.assertTrue(data_frame.empty)

        with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix", return_value=""):
            with patch(
                "masu.processor.parquet.parquet_report_processor.remove_files_not_in_set_from_s3_bucket"
            ) as mock_remove:
                with patch(
                    "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor." "convert_csv_to_parquet"
                ) as mock_convert:
                    with patch(
                        "masu.processor.parquet.parquet_report_processor."
                        "ReportManifestDBAccessor.get_s3_parquet_cleared",
                        return_value=False,
                    ) as mock_get_cleared:
                        with patch(
                            "masu.processor.parquet.parquet_report_processor."
                            "ReportManifestDBAccessor.mark_s3_parquet_cleared"
                        ) as mock_mark_cleared:
                            with patch.object(ParquetReportProcessor, "create_daily_parquet"):
                                mock_convert.return_value = "", pd.DataFrame(), True
                                self.report_processor.convert_to_parquet()
                                mock_get_cleared.assert_called()
                                mock_remove.assert_called()
                                mock_mark_cleared.assert_called()

        expected = "Failed to convert the following files to parquet"
        with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix", return_value=""):
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet",
                return_value=("", pd.DataFrame(), False),
            ):
                with patch.object(ParquetReportProcessor, "create_daily_parquet"):
                    with self.assertLogs("masu.processor.parquet.parquet_report_processor", level="INFO") as logger:
                        self.report_processor.convert_to_parquet()
                        self.assertIn(expected, " ".join(logger.output))

        with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix", return_value=""):
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet",
                return_value=("", pd.DataFrame(), False),
            ):
                with patch.object(ParquetReportProcessor, "create_daily_parquet"):
                    self.report_processor.convert_to_parquet()

        with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix", return_value=""):
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet",
                return_value=("", pd.DataFrame(), False),
            ):
                with patch.object(ParquetReportProcessor, "create_daily_parquet"):
                    self.report_processor.convert_to_parquet()

        # Daily data exists
        with patch("masu.processor.parquet.parquet_report_processor.get_path_prefix", return_value=""):
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_csv_to_parquet",
                return_value=("", pd.DataFrame([{"key": "value"}]), True),
            ):
                with patch.object(ParquetReportProcessor, "create_daily_parquet") as mock_create_daily:
                    file_name, data_frame = self.report_processor.convert_to_parquet()
                    call_args = mock_create_daily.call_args
                    self.assertTrue(call_args.equals(data_frame[0]))

    @patch("masu.processor.parquet.parquet_report_processor.os.path.exists")
    @patch("masu.processor.parquet.parquet_report_processor.os.remove")
    def test_convert_csv_to_parquet(self, mock_remove, mock_exists):
        """Test convert_csv_to_parquet."""
        _, __, result = self.report_processor.convert_csv_to_parquet("file.csv")
        self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.Path"):
            with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                mock_os.path.split.return_value = ("path", "file.csv.gz")
                _, __, result = self.report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
                self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.Path"):
            with patch("masu.processor.parquet.parquet_report_processor.pd") as mock_pd:
                with patch("masu.processor.parquet.parquet_report_processor.open") as mock_open:
                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                        mock_os.path.split.return_value = ("path", "file.csv.gz")
                        mock_pd.read_csv.return_value.__enter__.return_value = [1, 2, 3]
                        mock_open.side_effect = ValueError()
                        _, __, result = self.report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
                        self.assertFalse(result)

        with patch("masu.processor.parquet.parquet_report_processor.Path"):
            with patch("masu.processor.parquet.parquet_report_processor.pd") as mock_pd:
                with patch("masu.processor.parquet.parquet_report_processor.open", side_effect=Exception):
                    with patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"):
                        with patch(
                            "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor."
                            "create_parquet_table"
                        ):
                            with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                                mock_os.path.split.return_value = ("path", "file.csv.gz")
                                mock_pd.read_csv.return_value.__enter__.return_value = [1, 2, 3]
                                # mock_copy.side_effect = Exception
                                _, __, result = self.report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
                                self.assertFalse(result)

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
                                _, __, result = self.report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
                                self.assertTrue(result)

        with patch("masu.processor.parquet.parquet_report_processor.Path"):
            with patch("masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"):
                with patch(
                    "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor." "create_parquet_table"
                ):
                    with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                        mock_os.path.split.return_value = ("path", "file.csv")
                        test_report_test_path = "./koku/masu/test/data/test_cur.csv.gz"
                        local_path = f"{Config.TMP_DIR}/{self.account_id}/{self.aws_provider_uuid}"
                        Path(local_path).mkdir(parents=True, exist_ok=True)
                        test_report = f"{local_path}/test_cur.csv.gz"
                        shutil.copy2(test_report_test_path, test_report)

                        report_processor = ParquetReportProcessor(
                            schema_name=self.schema,
                            report_path=test_report,
                            provider_uuid=self.aws_provider_uuid,
                            provider_type=Provider.PROVIDER_AWS_LOCAL,
                            manifest_id=self.manifest_id,
                            context={
                                "tracing_id": self.tracing_id,
                                "start_date": DateHelper().today,
                                "create_table": True,
                            },
                        )
                        _, __, result = report_processor.convert_csv_to_parquet(test_report)
                        self.assertTrue(result)
                        shutil.rmtree(local_path, ignore_errors=True)

    def test_convert_csv_to_parquet_report_type_already_processed(self):
        """Test that we don't re-create a table when we already have created this run."""
        with patch("masu.processor.parquet.parquet_report_processor.Path"), patch(
            "masu.processor.parquet.parquet_report_processor.pd"
        ), patch("masu.processor.parquet.parquet_report_processor.open"), patch(
            "masu.processor.parquet.parquet_report_processor.copy_data_to_s3_bucket"
        ), patch(
            "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.set_post_processor",
            return_value=OCPPostProcessor(self.schema, "pod_usage"),
        ):
            with patch(
                "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor." "create_parquet_table"
            ) as mock_create_table:
                with patch("masu.processor.parquet.parquet_report_processor.os") as mock_os:
                    mock_os.path.split.return_value = ("path", "file.csv")
                    report_processor = ParquetReportProcessor(
                        schema_name=self.schema,
                        report_path="pod_usage.csv",
                        provider_uuid=self.ocp_provider_uuid,
                        provider_type=Provider.PROVIDER_OCP,
                        manifest_id=self.manifest_id,
                        context={
                            "tracing_id": self.tracing_id,
                            "start_date": DateHelper().today,
                            "create_table": True,
                        },
                    )
                    report_processor.trino_table_exists["pod_usage"] = True
                    result = report_processor.convert_csv_to_parquet("csv_filename.csv.gz")
                    self.assertTrue(result)
                    mock_create_table.assert_not_called()

    @patch.object(ParquetReportProcessor, "report_type", new_callable=PropertyMock)
    @patch.object(ReportParquetProcessorBase, "sync_hive_partitions")
    @patch.object(ReportParquetProcessorBase, "get_or_create_postgres_partition")
    @patch.object(ReportParquetProcessorBase, "table_exists")
    @patch.object(ReportParquetProcessorBase, "schema_exists")
    @patch.object(ReportParquetProcessorBase, "create_schema")
    @patch.object(ReportParquetProcessorBase, "create_table")
    def test_create_parquet_table(
        self,
        mock_create_table,
        mock_create_schema,
        mock_schema_exists,
        mock_table_exists,
        mock_partition,
        mock_sync,
        mock_report_type,
    ):
        """Test create_parquet_table function."""
        test_matrix = [
            {
                "provider_uuid": str(self.aws_provider_uuid),
                "provider_type": Provider.PROVIDER_AWS,
                "patch": (AWSReportParquetProcessor, "create_bill"),
                "daily": False,
            },
            {
                "provider_uuid": str(self.aws_provider_uuid),
                "provider_type": Provider.PROVIDER_AWS,
                "patch": (AWSReportParquetProcessor, "create_bill"),
                "daily": True,
            },
            {
                "provider_uuid": str(self.ocp_provider_uuid),
                "provider_type": Provider.PROVIDER_OCP,
                "report_file": "pod_usage.csv",
                "patch": (OCPReportParquetProcessor, "create_bill"),
                "daily": True,
            },
            {
                "provider_uuid": str(self.ocp_provider_uuid),
                "provider_type": Provider.PROVIDER_OCP,
                "report_file": "pod_usage.csv",
                "patch": (OCPReportParquetProcessor, "create_bill"),
                "daily": False,
            },
            {
                "provider_uuid": str(self.azure_provider_uuid),
                "provider_type": Provider.PROVIDER_AZURE,
                "patch": (AzureReportParquetProcessor, "create_bill"),
            },
            {
                "provider_uuid": str(self.gcp_provider_uuid),
                "provider_type": Provider.PROVIDER_GCP,
                "patch": (GCPReportParquetProcessor, "create_bill"),
            },
            {
                "provider_uuid": str(self.oci_provider_uuid),
                "provider_type": Provider.PROVIDER_OCI,
                "report_file": "usage.csv",
                "patch": (OCIReportParquetProcessor, "create_bill"),
                "daily": False,
            },
            {
                "provider_uuid": str(self.oci_provider_uuid),
                "provider_type": Provider.PROVIDER_OCI,
                "report_file": "usage.csv",
                "patch": (OCIReportParquetProcessor, "create_bill"),
                "daily": True,
            },
        ]
        output_file = "local_path/file.parquet"

        mock_schema_exists.return_value = False
        mock_table_exists.return_value = False

        for test in test_matrix:
            if test.get("provider_type") == Provider.PROVIDER_OCP:
                mock_report_type.return_value = "pod_usage"
            elif test.get("provider_type") == Provider.PROVIDER_OCI:
                mock_report_type.return_value = "usage"
            else:
                mock_report_type.return_value = None
            provider_uuid = test.get("provider_uuid")
            provider_type = test.get("provider_type")
            patch_class, patch_method = test.get("patch")
            with patch.object(patch_class, patch_method) as mock_create_bill:
                report_processor = ParquetReportProcessor(
                    schema_name=self.schema,
                    report_path=test.get("report_file") or self.report_path,
                    provider_uuid=provider_uuid,
                    provider_type=provider_type,
                    manifest_id=self.manifest_id,
                    context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "create_table": True},
                )
                report_processor.create_parquet_table(output_file, daily=test.get("daily"))
                if test.get("daily"):
                    mock_create_bill.assert_not_called()
                else:
                    mock_create_bill.assert_called()
                mock_schema_exists.assert_called()
                mock_table_exists.assert_called()
                mock_create_schema.assert_called()
                mock_create_table.assert_called()
                mock_partition.assert_called()
                mock_sync.assert_called()
            mock_report_type.reset_mock()
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

        output_file = "local_path/file.parquet"

        mock_schema_exists.return_value = True
        mock_table_exists.return_value = True

        self.report_processor.create_parquet_table(output_file)

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
        mock_convert.return_value = "", pd.DataFrame()
        self.report_processor.process()
        mock_convert.assert_called()
        mock_convert.reset_mock()

        file_list = ["path/to/file_one", "path/to/file_two", "path/to/file_three"]
        ocp_processor = ParquetReportProcessor(
            schema_name=self.schema,
            report_path=f"/my/{self.test_assembly_id}/{self.report_name}",
            provider_uuid=self.ocp_provider_uuid,
            provider_type=Provider.PROVIDER_OCP,
            manifest_id=self.manifest_id,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "split_files": file_list},
        )
        ocp_processor.process()
        mock_convert.assert_called()

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
            provider_uuid=self.gcp_provider_uuid,
            provider_type=Provider.PROVIDER_GCP,
            manifest_id=self.manifest_id,
            context={"tracing_id": self.tracing_id, "start_date": DateHelper().today, "split_files": file_list},
        )

        with patch(
            "masu.processor.parquet.parquet_report_processor.ParquetReportProcessor.convert_to_parquet"
        ) as mock_convert:
            mock_convert.return_value = "", pd.DataFrame()
            gcp_processor.process()
            mock_convert.assert_called()

        gcp_processor.process()

        self.assertFalse(os.path.exists(report_path))
        for path in file_list:
            self.assertFalse(os.path.exists(report_path))

    @patch.object(ParquetReportProcessor, "create_parquet_table")
    @patch.object(ParquetReportProcessor, "_write_parquet_to_file")
    def test_create_daily_parquet(self, mock_write, mock_create_table):
        """Test the daily parquet method."""
        self.report_processor.create_daily_parquet("", [pd.DataFrame()])
        mock_write.assert_called()
        mock_create_table.assert_called()
