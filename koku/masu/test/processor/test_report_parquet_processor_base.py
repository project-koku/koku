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
        self.account = 10001
        self.s3_path = self.temp_dir
        self.provider_uuid = str(uuid.uuid4())
        self.local_parquet = self.output_file
        self.date_columns = ["date1", "date2"]
        self.numeric_columns = ["numeric1", "numeric2"]
        self.other_columns = ["other"]
        self.table_name = "test_table"
        self.processor = ReportParquetProcessorBase(
            self.manifest_id,
            self.account,
            self.s3_path,
            self.provider_uuid,
            self.local_parquet,
            self.numeric_columns,
            self.date_columns,
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
        expected_schema_name = f"acct{10001}"
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

    @patch("masu.processor.report_parquet_processor_base.ReportParquetProcessorBase._execute_sql")
    def test_create_table(self, mock_execute):
        """Test the Presto/Hive create table method."""
        expected_log = (
            "INFO:masu.processor.report_parquet_processor_base:"
            f"CALL system.sync_partition_metadata('{self.processor._schema_name}', "
            f"'{self.processor._table_name}', 'FULL')"
        )
        expected_table_log = (
            f"INFO:masu.processor.report_parquet_processor_base:Presto Table: {self.processor._table_name} created."
        )
        with self.assertLogs("masu.processor.report_parquet_processor_base", level="INFO") as logger:
            self.processor.create_table()
            self.assertIn(expected_log, logger.output)
            self.assertIn(expected_table_log, logger.output)
