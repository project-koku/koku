#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the hcs_report_data endpoint view."""
import os
import shutil
import tempfile
from datetime import datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from masu.api.upgrade_trino.util.state_tracker import StateTracker
from masu.api.upgrade_trino.util.verify_parquet_files import VerifyParquetFiles
from masu.test import MasuTestCase


class TestVerifyParquetFiles(MasuTestCase):
    def setUp(self):
        super().setUp()
        # Experienced issues with pyarrow not
        # playing nice with tempfiles. Therefore
        # I opted for writing files to a tmp dir
        self.temp_dir = tempfile.mkdtemp()
        self.required_columns = {"float": 0.0, "string": "", "datetime": pd.NaT}
        self.expected_pyarrow_dtypes = {"float": pa.float64(), "string": pa.string(), "datetime": pa.timestamp("ms")}
        self.panda_kwargs = {"allow_truncated_timestamps": True, "coerce_timestamps": "ms", "index": False}
        self.suffix = ".parquet"

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def create_default_verify_handler(self):
        verify_parquet_file_kwargs = {
            "schema_name": self.schema_name,
            "provider_uuid": self.aws_provider_uuid,
            "provider_type": self.aws_provider.type,
            "simulate": True,
            "bill_date": datetime(2023, 1, 1),
            "cleaned_column_mapping": self.required_columns,
        }
        return VerifyParquetFiles(**verify_parquet_file_kwargs)

    def test_coerce_parquet_data_type_no_changes_needed(self):
        """Test a parquet file with correct dtypes."""
        file_data = {
            "float": [1.1, 2.2, 3.3],
            "string": ["A", "B", "C"],
            "datetime": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
            "unrequired_column": ["a", "b", "c"],
        }
        with tempfile.NamedTemporaryFile(suffix=self.suffix) as temp_file:
            pd.DataFrame(file_data).to_parquet(temp_file, **self.panda_kwargs)
            verify_handler = self.create_default_verify_handler()
            verify_handler.file_tracker.add_local_file(temp_file.name, temp_file)
            return_state = verify_handler._coerce_parquet_data_type(temp_file)
            self.assertEqual(return_state, StateTracker.NO_CHANGES_NEEDED)

    def test_coerce_parquet_data_type_coerce_needed(self):
        """Test that files created through reindex are fixed correctly."""
        data_frame = pd.DataFrame()
        data_frame = data_frame.reindex(columns=self.required_columns.keys())
        temp_file = os.path.join(self.temp_dir, f"test{self.suffix}")
        data_frame.to_parquet(temp_file, **self.panda_kwargs)
        verify_handler = self.create_default_verify_handler()
        verify_handler.file_tracker.add_local_file(temp_file, temp_file)
        return_state = verify_handler._coerce_parquet_data_type(temp_file)
        self.assertEqual(return_state, StateTracker.COERCE_REQUIRED)
        table = pq.read_table(temp_file)
        schema = table.schema
        for field in schema:
            self.assertEqual(field.type, self.expected_pyarrow_dtypes.get(field.name))
        os.remove(temp_file)

    def test_coerce_parquet_data_type_failed_to_coerce(self):
        """Test a parquet file with correct dtypes."""
        file_data = {
            "float": [datetime(2023, 1, 1), datetime(2023, 1, 1), datetime(2023, 1, 1)],
            "string": ["A", "B", "C"],
            "datetime": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
        }
        with tempfile.NamedTemporaryFile(suffix=self.suffix) as temp_file:
            pd.DataFrame(file_data).to_parquet(temp_file, **self.panda_kwargs)
            verify_handler = self.create_default_verify_handler()
            verify_handler.file_tracker.add_local_file(temp_file.name, temp_file)
            return_state = verify_handler._coerce_parquet_data_type(temp_file)
            self.assertEqual(return_state, StateTracker.FAILED_DTYPE_CONVERSION)
