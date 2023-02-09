#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportParquetProcessorBase."""
import shutil
import tempfile
import uuid
from unittest.mock import patch

import pandas as pd
from django.test.utils import override_settings

from masu.processor.report_parquet_processor_base import PostgresSummaryTableError
from masu.processor.report_parquet_processor_base import ReportParquetProcessorBase
from masu.test import MasuTestCase


class ReportParquetProcessorBaseTest(MasuTestCase):
    """Test cases for the ReportParquetProcessorBase."""

    @classmethod
    def setUpClass(cls):
        """Setup the test class with required objects."""
        super().setUpClass()
        cls.csv_path = "./koku/masu/test/data/parquet_input.csv"

    def setUp(self):
        """Setup up shared variables."""
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.csv_col_names = pd.read_csv(self.csv_path, nrows=0).columns
        data_frame = pd.read_csv(self.csv_path)
        self.parquet_file_name = "test.parquet"
        self.output_file = f"{self.temp_dir}/{self.parquet_file_name}"
        data_frame.to_parquet(self.output_file, allow_truncated_timestamps=True, coerce_timestamps="ms")

        self.manifest_id = 1
        self.account = "org1234567"
        self.s3_path = self.temp_dir
        self.provider_uuid = str(uuid.uuid4())
        self.local_parquet = self.output_file
        self.date_columns = ["date1", "date2"]
        self.numeric_columns = ["numeric1", "numeric2"]
        self.boolean_columns = ["bool_col"]
        self.other_columns = ["other"]
        self.table_name = "test_table"
        self.column_types = {
            "numeric_columns": self.numeric_columns,
            "date_columns": self.date_columns,
            "boolean_columns": self.boolean_columns,
        }
        self.processor = ReportParquetProcessorBase(
            self.manifest_id,
            self.account,
            self.s3_path,
            self.provider_uuid,
            self.local_parquet,
            self.column_types,
            self.table_name,
        )

    def tearDown(self):
        """Cleanup test case."""
        super().tearDown()
        shutil.rmtree(self.temp_dir)

    def test_table_name(self):
        """Test the parquet table generated name."""
        expected_table_name = self.table_name
        self.assertEqual(self.processor._table_name, expected_table_name)

    def test_schema_name(self):
        """Test the account to schema name generation."""
        expected_schema_name = "org1234567"
        self.assertEqual(self.processor._schema_name, expected_schema_name)

    def test_generate_column_list(self):
        """Test the generate_column_list helper."""
        self.assertEqual(len(self.processor._generate_column_list()), len(self.csv_col_names))

    def test_postgres_summary_table(self):
        """Test that the unimplemented property raises an error."""
        with self.assertRaises(PostgresSummaryTableError):
            self.processor.postgres_summary_table

    @override_settings(S3_BUCKET_NAME="test-bucket")
    @patch("masu.processor.aws.aws_report_parquet_processor.ReportParquetProcessorBase._execute_sql")
    def test_generate_create_table_sql(self, mock_execute):
        """Test the generate parquet table sql."""
        generated_sql = self.processor._generate_create_table_sql()

        expected_start = f"CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name}"
        expected_end = (
            f"WITH(external_location = 's3a://test-bucket/{self.temp_dir}', "
            "format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month'])"
        )
        self.assertTrue(generated_sql.startswith(expected_start))
        for num_col in self.numeric_columns:
            self.assertIn(f"{num_col} double", generated_sql)
        for date_col in self.date_columns:
            self.assertIn(f"{date_col} timestamp", generated_sql)
        for other_col in self.other_columns:
            self.assertIn(f"{other_col} varchar", generated_sql)
        self.assertTrue(generated_sql.endswith(expected_end))

    @override_settings(S3_BUCKET_NAME="test-bucket")
    @patch("masu.processor.aws.aws_report_parquet_processor.ReportParquetProcessorBase._execute_sql")
    def test_generate_create_table_sql_with_provider_map(self, mock_execute):
        """Test the generate parquet table sql."""
        partition_map = {
            "source": "varchar",
            "year": "varchar",
            "month": "varchar",
            "day": "varchar",
        }
        generated_sql = self.processor._generate_create_table_sql(partition_map=partition_map)

        expected_start = f"CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name}"
        expected_end = (
            f"WITH(external_location = 's3a://test-bucket/{self.temp_dir}', "
            "format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month', 'day'])"
        )
        self.assertTrue(generated_sql.startswith(expected_start))
        for num_col in self.numeric_columns:
            self.assertIn(f"{num_col} double", generated_sql)
        for date_col in self.date_columns:
            self.assertIn(f"{date_col} timestamp", generated_sql)
        for other_col in self.other_columns:
            self.assertIn(f"{other_col} varchar", generated_sql)
        self.assertTrue(generated_sql.endswith(expected_end))

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_create_table(self, mock_execute):
        """Test the Presto/Hive create table method."""
        expected_log = f"Table: {self.processor._table_name} created."
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.create_table()
            self.assertTrue(any(expected_log in log for log in logger.output))

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_sync_hive_partitions(self, mock_execute):
        """Test that hive partitions are synced."""
        expected_log = (
            "INFO:masu.processor.report_parquet_processor_base:"
            f"CALL system.sync_partition_metadata('{self.processor._schema_name}', "
            f"'{self.processor._table_name}', 'FULL')"
        )
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.sync_hive_partitions()
            self.assertIn(expected_log, logger.output)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_schema_exists(self, mock_execute):
        """Test that hive partitions are synced."""
        expected_log = "INFO:masu.processor.report_parquet_processor_base:" "Checking for schema"
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.schema_exists()
            self.assertIn(expected_log, logger.output)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_table_exists(self, mock_execute):
        """Test that hive partitions are synced."""
        expected_log = "INFO:masu.processor.report_parquet_processor_base:" "Checking for table"
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.table_exists()
            self.assertIn(expected_log, logger.output)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_create_schema(self, mock_execute):
        """Test that hive partitions are synced."""
        expected_log = (
            "INFO:masu.processor.report_parquet_processor_base:"
            f"Create Trino/Hive schema SQL: CREATE SCHEMA IF NOT EXISTS {self.account}"
        )
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.create_schema()
            self.assertIn(expected_log, logger.output)
