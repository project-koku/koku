#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the ReportParquetProcessorBase."""
import shutil
import tempfile
import uuid
from datetime import date
from unittest.mock import call
from unittest.mock import MagicMock
from unittest.mock import patch

import pandas as pd
from django.conf import settings
from django.db import Error
from django.db import ProgrammingError
from django.test.utils import override_settings
from trino.exceptions import TrinoQueryError

from api.common import log_json
from koku.cache import build_trino_schema_exists_key
from koku.cache import build_trino_table_exists_key
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
        self.start_date = date(2024, 1, 15)
        self.processor = ReportParquetProcessorBase(
            self.manifest_id,
            self.account,
            self.s3_path,
            self.provider_uuid,
            self.column_types,
            self.table_name,
            self.start_date,
        )
        self.log_base = "masu.processor.report_parquet_processor_base"
        self.log_output_info = f"INFO:{self.log_base}:"

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

    def test_postgres_summary_table(self):
        """Test that the unimplemented property raises an error."""
        with self.assertRaises(PostgresSummaryTableError):
            self.processor.postgres_summary_table

    @override_settings(S3_BUCKET_NAME="test-bucket")
    @patch("masu.processor.aws.aws_report_parquet_processor.ReportParquetProcessorBase._execute_trino_sql")
    def test_generate_create_table_sql(self, mock_execute):
        """Test the generate parquet table sql."""
        generated_sql = self.processor._generate_create_table_sql(self.csv_col_names)

        expected_start = f"CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name}"
        expected_end = (
            f"WITH(external_location = '{settings.TRINO_S3A_OR_S3}://test-bucket/{self.temp_dir}', "
            "format = 'PARQUET', partitioned_by=ARRAY['source', 'year', 'month'])"
        )
        self.assertTrue(generated_sql.startswith(expected_start))
        for num_col in self.numeric_columns:
            self.assertIn(f"{num_col} double", generated_sql)
        for date_col in self.date_columns:
            self.assertIn(f"{date_col} timestamp", generated_sql)
        for other_col in self.other_columns:
            self.assertIn(f"{other_col} varchar", generated_sql)
        self.assertTrue(
            generated_sql.endswith(expected_end),
            f"Expected to end with:\n{expected_end}\n\nActual SQL:\n{generated_sql}",
        )

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_trino_sql")
    def test_create_table(self, mock_execute):
        """Test the Trino/Hive create table method."""
        expected_logs = []
        for log in ["attempting to create parquet table", "trino parquet table created"]:
            expected_log = self.log_output_info + str(
                log_json(msg=log, table=self.table_name, schema=self.schema_name)
            )
            expected_logs.append(expected_log)
        with self.assertLogs(self.log_base, level="INFO") as logger:
            self.processor.create_table(self.csv_col_names)
            for expected_log in expected_logs:
                self.assertIn(expected_log, logger.output)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_trino_sql_with_retries")
    def test_sync_hive_partitions(self, mock_execute):
        """Given a processor with a valid schema and table,
        when sync_hive_partitions is called,
        then it logs the sync attempt and delegates to _execute_trino_sql_with_retries.
        """
        expected_log = self.log_output_info + str(
            log_json(msg="syncing trino/hive partitions", schema=self.schema_name, table=self.table_name)
        )
        with self.assertLogs(self.log_base, level="INFO") as logger:
            self.processor.sync_hive_partitions()
            self.assertIn(expected_log, logger.output)
        expected_sql = f"CALL system.sync_partition_metadata('{self.schema_name}', '{self.table_name}', 'FULL')"
        mock_execute.assert_called_once_with(expected_sql, self.schema_name, caller="sync_hive_partitions")

    def _mock_trino_accessor(self, mock_accessor, mock_cursor):
        """Configure mock_accessor to return mock_cursor through the connection context managers."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_accessor.return_value.connect.return_value.__enter__.return_value = mock_conn

    @patch("masu.processor.report_parquet_processor_base.random.uniform", return_value=0.5)
    @patch("masu.processor.report_parquet_processor_base.time.sleep")
    @patch("masu.processor.report_parquet_processor_base.get_report_db_accessor")
    def test_execute_trino_sql_with_retries_retries_on_trino_query_error(
        self, mock_accessor, mock_sleep, mock_uniform
    ):
        """Given a TrinoQueryError on every attempt,
        when _execute_trino_sql_with_retries is called with max_retries=2,
        then it retries 2 times (3 total attempts), sleeps between each, and returns [].
        """
        mock_cursor = MagicMock()
        trino_error = TrinoQueryError(
            {"errorName": "ALREADY_EXISTS", "message": "One or more Partitions Already exist"}
        )
        mock_cursor.execute.side_effect = trino_error
        self._mock_trino_accessor(mock_accessor, mock_cursor)

        with self.assertLogs(self.log_base, level="WARNING") as cm:
            result = self.processor._execute_trino_sql_with_retries(
                "SELECT 1", self.schema_name, caller="test", max_retries=2
            )
        self.assertEqual(result, [])
        self.assertEqual(mock_cursor.execute.call_count, 3)
        # Backoff is 2**attempt + 0.5: attempt 0 -> 1.5, attempt 1 -> 2.5
        self.assertEqual(mock_sleep.call_args_list, [call(1.5), call(2.5)])
        warning_logs = [o for o in cm.output if "retrying (attempt" in o]
        self.assertEqual(len(warning_logs), 2)
        self.assertIn(self.schema_name, warning_logs[0])
        error_logs = [o for o in cm.output if "failed after 3 attempts" in o]
        self.assertEqual(len(error_logs), 1)

    @patch("masu.processor.report_parquet_processor_base.time.sleep")
    @patch("masu.processor.report_parquet_processor_base.get_report_db_accessor")
    def test_execute_trino_sql_with_retries_no_retry_on_non_retryable_errors(self, mock_accessor, mock_sleep):
        """Given a non-retryable error (ProgrammingError or Django Error),
        when _execute_trino_sql_with_retries is called,
        then it logs the error and returns [] without retrying.
        """
        cases = [
            {"error": ProgrammingError("bad sql"), "log_level": "WARNING"},
            {"error": Error("django error"), "log_level": "ERROR"},
        ]
        for case in cases:
            with self.subTest(error=type(case["error"]).__name__):
                mock_accessor.reset_mock()
                mock_sleep.reset_mock()
                mock_cursor = MagicMock()
                mock_cursor.execute.side_effect = case["error"]
                self._mock_trino_accessor(mock_accessor, mock_cursor)

                with self.assertLogs(self.log_base, level=case["log_level"]) as cm:
                    result = self.processor._execute_trino_sql_with_retries(
                        "SELECT 1", self.schema_name, caller="test", max_retries=2
                    )
                self.assertEqual(result, [])
                self.assertEqual(mock_cursor.execute.call_count, 1)
                non_retryable_logs = [o for o in cm.output if "non-retryable error" in o]
                self.assertEqual(len(non_retryable_logs), 1)
                self.assertIn(self.schema_name, non_retryable_logs[0])
                self.assertIn("test", non_retryable_logs[0])
                mock_sleep.assert_not_called()

    @patch("masu.processor.report_parquet_processor_base.random.uniform", return_value=0.5)
    @patch("masu.processor.report_parquet_processor_base.time.sleep")
    @patch("masu.processor.report_parquet_processor_base.get_report_db_accessor")
    def test_execute_trino_sql_with_retries_succeeds_after_retry(self, mock_accessor, mock_sleep, mock_uniform):
        """Given a TrinoQueryError on the first attempt and success on the second,
        when _execute_trino_sql_with_retries is called,
        then it retries once, sleeps once, and returns the rows from the successful attempt.
        """
        trino_error = TrinoQueryError(
            {"errorName": "ALREADY_EXISTS", "message": "One or more Partitions Already exist"}
        )
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [trino_error, None]
        mock_cursor.fetchall.return_value = [("ok",)]
        self._mock_trino_accessor(mock_accessor, mock_cursor)

        with self.assertLogs(self.log_base, level="WARNING") as cm:
            result = self.processor._execute_trino_sql_with_retries(
                "SELECT 1", self.schema_name, caller="test", max_retries=2
            )
        self.assertEqual(result, [("ok",)])
        self.assertEqual(mock_cursor.execute.call_count, 2)
        # Backoff is 2**0 + 0.5 -> 1.5
        mock_sleep.assert_called_once_with(1.5)
        warning_logs = [o for o in cm.output if "retrying (attempt 1)" in o]
        self.assertEqual(len(warning_logs), 1)
        self.assertIn(self.schema_name, warning_logs[0])

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_schema_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.processor.report_parquet_processor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.processor.schema_exists())
            trino_mock.assert_not_called()

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_schema_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        key = build_trino_schema_exists_key(self.account)
        with patch("masu.processor.report_parquet_processor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.processor.schema_exists())
            mock_cache_set.assert_called_with(key, True)

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_schema_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        key = build_trino_schema_exists_key(self.account)
        with patch("masu.processor.report_parquet_processor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.processor.schema_exists())
            mock_cache_set.assert_called_with(key, False)

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_table_exists_cache_value_in_cache(self, trino_mock):
        with patch(
            "masu.processor.report_parquet_processor_base.get_value_from_cache",
            return_value=True,
        ):
            self.assertTrue(self.processor.table_exists())
            trino_mock.assert_not_called()

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_table_exists_cache_value_not_in_cache(self, trino_mock):
        trino_mock.return_value = True
        key = build_trino_table_exists_key(self.account, self.table_name)
        with patch("masu.processor.report_parquet_processor_base.set_value_in_cache") as mock_cache_set:
            self.assertTrue(self.processor.table_exists())
            mock_cache_set.assert_called_with(key, True)

    @patch.object(ReportParquetProcessorBase, "_execute_trino_sql")
    def test_table_exists_cache_value_not_in_cache_not_exists(self, trino_mock):
        trino_mock.return_value = False
        key = build_trino_table_exists_key(self.account, self.table_name)
        with patch("masu.processor.report_parquet_processor_base.set_value_in_cache") as mock_cache_set:
            self.assertFalse(self.processor.table_exists())
            mock_cache_set.assert_called_with(key, False)

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_trino_sql")
    def test_create_schema(self, mock_execute):
        """Test that hive partitions are synced."""
        expected_log = self.log_output_info + str(
            log_json(msg="create trino/hive schema sql", schema=self.schema_name)
        )
        with self.assertLogs(self.log_base, level="INFO") as logger:
            self.processor.create_schema()
            self.assertIn(expected_log, logger.output)
