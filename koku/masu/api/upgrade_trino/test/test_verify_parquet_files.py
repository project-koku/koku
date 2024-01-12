#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the verify parquet files endpoint view."""
import os
import shutil
import tempfile
from collections import namedtuple
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from api.utils import DateHelper
from masu.api.upgrade_trino.util.constants import ConversionContextKeys
from masu.api.upgrade_trino.util.constants import ConversionStates
from masu.api.upgrade_trino.util.constants import CONVERTER_VERSION
from masu.api.upgrade_trino.util.task_handler import FixParquetTaskHandler
from masu.api.upgrade_trino.util.verify_parquet_files import VerifyParquetFiles
from masu.celery.tasks import PROVIDER_REPORT_TYPE_MAP
from masu.config import Config
from masu.test import MasuTestCase
from masu.util.common import get_path_prefix

DummyS3Object = namedtuple("DummyS3Object", "key")


class TestVerifyParquetFiles(MasuTestCase):
    def setUp(self):
        super().setUp()
        # Experienced issues with pyarrow not
        # playing nice with tempfiles. Therefore
        # I opted for writing files to a tmp dir
        self.temp_dir = tempfile.mkdtemp()
        self.required_columns = {"float": 0.0, "string": "", "datetime": pd.NaT}
        self.expected_pyarrow_dtypes = {
            "float": pa.float64(),
            "string": pa.string(),
            "datetime": pa.timestamp("ms"),
        }
        self.panda_kwargs = {
            "allow_truncated_timestamps": True,
            "coerce_timestamps": "ms",
            "index": False,
        }
        self.suffix = ".parquet"
        self.bill_date = str(DateHelper().this_month_start)
        self.default_provider = self.azure_provider

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def create_default_verify_handler(self):
        return VerifyParquetFiles(
            schema_name=self.schema_name,
            provider_uuid=str(self.default_provider.uuid),
            provider_type=self.default_provider.type,
            simulate=True,
            bill_date=self.bill_date,
            cleaned_column_mapping=self.required_columns,
        )

    def build_expected_additional_context(self, verify_hander, successful=True):
        return {
            ConversionContextKeys.metadata: {
                verify_hander.file_tracker.bill_date_str: {
                    ConversionContextKeys.version: CONVERTER_VERSION,
                    ConversionContextKeys.successful: successful,
                }
            }
        }

    def verify_correct_types(self, temp_file, verify_handler):
        table = pq.read_table(temp_file)
        schema = table.schema
        for field in schema:
            self.assertEqual(field.type, verify_handler.required_columns.get(field.name))

    @patch("masu.api.upgrade_trino.util.verify_parquet_files.StateTracker._clean_local_files")
    @patch("masu.api.upgrade_trino.util.verify_parquet_files.get_s3_resource")
    def test_retrieve_verify_reload_s3_parquet(self, mock_s3_resource, _):
        """Test fixes for reindexes on all required columns."""
        # build a parquet file where reindex is used for all required columns

        def create_tmp_test_file(provider, required_columns):
            """Creates a parquet file with all empty required columns through reindexing."""
            data_frame = pd.DataFrame()
            data_frame = data_frame.reindex(columns=required_columns.keys())
            filename = f"test_{str(provider.uuid)}{self.suffix}"
            temp_file = os.path.join(self.temp_dir, filename)
            data_frame.to_parquet(temp_file, **self.panda_kwargs)
            return temp_file

        attributes = ["aws_provider", "azure_provider", "ocp_provider", "oci_provider"]
        for attr in attributes:
            with self.subTest(attr=attr):
                provider = getattr(self, attr)
                required_columns = FixParquetTaskHandler.clean_column_names(provider.type)
                temp_file = create_tmp_test_file(provider, required_columns)
                mock_bucket = mock_s3_resource.return_value.Bucket.return_value
                verify_handler = VerifyParquetFiles(
                    schema_name=self.schema_name,
                    provider_uuid=str(provider.uuid),
                    provider_type=provider.type,
                    simulate=False,
                    bill_date=self.bill_date,
                    cleaned_column_mapping=required_columns,
                )
                conversion_metadata = provider.additional_context.get(ConversionContextKeys.metadata, {})
                self.assertTrue(verify_handler.file_tracker.add_to_queue(conversion_metadata))
                prefixes = verify_handler._generate_s3_path_prefixes(DateHelper().this_month_start)
                filter_side_effect = [[DummyS3Object(key=temp_file)]]
                for _ in range(len(prefixes) - 1):
                    filter_side_effect.append([])
                mock_bucket.objects.filter.side_effect = filter_side_effect
                mock_bucket.download_file.return_value = temp_file
                VerifyParquetFiles.local_path = Path(self.temp_dir)
                verify_handler.retrieve_verify_reload_s3_parquet()
                mock_bucket.upload_fileobj.assert_called()
                self.verify_correct_types(temp_file, verify_handler)
                # Test that the additional context is set correctly
                provider.refresh_from_db()
                self.assertEqual(
                    provider.additional_context, self.build_expected_additional_context(verify_handler, True)
                )
                conversion_metadata = provider.additional_context.get(ConversionContextKeys.metadata)
                self.assertFalse(verify_handler.file_tracker.add_to_queue(conversion_metadata))

    def test_double_to_timestamp_transformation_with_reindex(self):
        """Test double to datetime transformation with values"""
        file_data = {
            "float": [1.1, 2.2, 3.3],
            "string": ["A", "B", "C"],
            "unrequired_column": ["a", "b", "c"],
        }
        test_file = "transformation_test.parquet"
        data_frame = pd.DataFrame(file_data)
        data_frame = data_frame.reindex(columns=self.required_columns)
        temp_file = os.path.join(self.temp_dir, test_file)
        data_frame.to_parquet(temp_file, **self.panda_kwargs)
        verify_handler = self.create_default_verify_handler()
        verify_handler._perform_transformation_double_to_timestamp(temp_file, ["datetime"])
        self.verify_correct_types(temp_file, verify_handler)

    def test_double_to_timestamp_transformation_with_values(self):
        """Test double to datetime transformation with values"""
        file_data = {
            "float": [1.1, 2.2, 3.3],
            "string": ["A", "B", "C"],
            "datetime": [1.1, 2.2, 3.3],
            "unrequired_column": ["a", "b", "c"],
        }
        test_file = "transformation_test.parquet"
        data_frame = pd.DataFrame(file_data)
        data_frame = data_frame.reindex(columns=self.required_columns)
        temp_file = os.path.join(self.temp_dir, test_file)
        data_frame.to_parquet(temp_file, **self.panda_kwargs)
        verify_handler = self.create_default_verify_handler()
        verify_handler._perform_transformation_double_to_timestamp(temp_file, ["datetime"])
        self.verify_correct_types(temp_file, verify_handler)

    @patch("masu.api.upgrade_trino.util.verify_parquet_files.StateTracker._clean_local_files")
    def test_coerce_parquet_data_type_no_changes_needed(self, _):
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
            verify_handler.file_tracker.set_state(temp_file.name, return_state)
            self.assertEqual(return_state, ConversionStates.no_changes_needed)
            bill_metadata = verify_handler.file_tracker._create_bill_date_metadata()
            self.assertTrue(bill_metadata.get(ConversionContextKeys.successful))
            # Test that generated messages would contain these files.
            simulated_messages = verify_handler.file_tracker.generate_simulate_messages()
            self.assertIn(str(temp_file.name), simulated_messages.get("Files that have all correct data_types."))

    def test_coerce_parquet_data_type_coerce_needed(self):
        """Test that files created through reindex are fixed correctly."""
        data_frame = pd.DataFrame()
        data_frame = data_frame.reindex(columns=self.required_columns.keys())
        filename = f"test{self.suffix}"
        temp_file = os.path.join(self.temp_dir, f"test{self.suffix}")
        data_frame.to_parquet(temp_file, **self.panda_kwargs)
        verify_handler = self.create_default_verify_handler()
        verify_handler.file_tracker.add_local_file(filename, Path(temp_file))
        return_state = verify_handler._coerce_parquet_data_type(temp_file)
        self.assertEqual(return_state, ConversionStates.coerce_required)
        verify_handler.file_tracker.set_state(filename, return_state)
        files_need_updating = verify_handler.file_tracker.get_files_that_need_updated()
        self.assertTrue(files_need_updating.get(filename))
        self.verify_correct_types(temp_file, verify_handler)
        # Test that generated messages would contain these files.
        simulated_messages = verify_handler.file_tracker.generate_simulate_messages()
        self.assertIn(filename, simulated_messages.get("Files that need to be updated."))
        # Test delete clean local files.
        verify_handler.file_tracker._clean_local_files()
        self.assertFalse(os.path.exists(temp_file))

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
            verify_handler.file_tracker.set_state(temp_file.name, return_state)
            self.assertEqual(return_state, ConversionStates.conversion_failed)
            verify_handler.file_tracker._check_if_complete()
            self.default_provider.refresh_from_db()
            conversion_metadata = self.default_provider.additional_context.get(ConversionContextKeys.metadata)
            self.assertIsNotNone(conversion_metadata)
            bill_metadata = conversion_metadata.get(verify_handler.file_tracker.bill_date_str)
            self.assertIsNotNone(bill_metadata)
            self.assertFalse(bill_metadata.get(ConversionContextKeys.successful), True)
            self.assertIsNotNone(bill_metadata.get(ConversionContextKeys.failed_files))
            # confirm nothing would be sent to s3
            self.assertEqual(verify_handler.file_tracker.get_files_that_need_updated(), {})
            # confirm that it should be retried on next run
            self.assertTrue(verify_handler.file_tracker.add_to_queue(conversion_metadata))

    def test_oci_s3_paths(self):
        """test path generation for oci sources."""
        bill_date = DateHelper().this_month_start
        expected_s3_paths = []
        for oci_report_type in PROVIDER_REPORT_TYPE_MAP.get(self.oci_provider.type):
            path_kwargs = {
                "account": self.schema_name,
                "provider_type": self.oci_provider.type.replace("-local", ""),
                "provider_uuid": self.oci_provider_uuid,
                "start_date": bill_date,
                "data_type": Config.PARQUET_DATA_TYPE,
                "report_type": oci_report_type,
            }
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
            path_kwargs["daily"] = True
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
        verify_handler = VerifyParquetFiles(
            schema_name=self.schema_name,
            provider_uuid=self.oci_provider_uuid,
            provider_type=self.oci_provider.type,
            simulate=True,
            bill_date=bill_date,
            cleaned_column_mapping=self.required_columns,
        )
        s3_prefixes = verify_handler._generate_s3_path_prefixes(bill_date)
        self.assertEqual(len(s3_prefixes), len(expected_s3_paths))
        for expected_path in expected_s3_paths:
            self.assertIn(expected_path, s3_prefixes)

    def test_ocp_s3_paths(self):
        """test path generation for ocp sources."""
        bill_date = DateHelper().this_month_start
        expected_s3_paths = []
        for ocp_report_type in PROVIDER_REPORT_TYPE_MAP.get(self.ocp_provider.type).keys():
            path_kwargs = {
                "account": self.schema_name,
                "provider_type": self.ocp_provider.type.replace("-local", ""),
                "provider_uuid": self.ocp_provider_uuid,
                "start_date": bill_date,
                "data_type": Config.PARQUET_DATA_TYPE,
                "report_type": ocp_report_type,
            }
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
            path_kwargs["daily"] = True
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
        verify_handler = VerifyParquetFiles(
            schema_name=self.schema_name,
            provider_uuid=self.ocp_provider_uuid,
            provider_type=self.ocp_provider.type,
            simulate=True,
            bill_date=bill_date,
            cleaned_column_mapping=self.required_columns,
        )
        s3_prefixes = verify_handler._generate_s3_path_prefixes(bill_date)
        self.assertEqual(len(s3_prefixes), len(expected_s3_paths))
        for expected_path in expected_s3_paths:
            self.assertIn(expected_path, s3_prefixes)

    def test_other_providers_s3_paths(self):
        def _build_expected_s3_paths(metadata):
            expected_s3_paths = []
            path_kwargs = {
                "account": self.schema_name,
                "provider_type": metadata["type"],
                "provider_uuid": metadata["uuid"],
                "start_date": bill_date,
                "data_type": Config.PARQUET_DATA_TYPE,
            }
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
            path_kwargs["daily"] = True
            path_kwargs["report_type"] = "raw"
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
            path_kwargs["report_type"] = "openshift"
            expected_s3_paths.append(get_path_prefix(**path_kwargs))
            return expected_s3_paths

        bill_date = DateHelper().this_month_start
        test_metadata = [
            {"uuid": self.aws_provider_uuid, "type": self.aws_provider.type.replace("-local", "")},
            {"uuid": self.azure_provider_uuid, "type": self.azure_provider.type.replace("-local", "")},
        ]
        for metadata in test_metadata:
            with self.subTest(metadata=metadata):
                expected_s3_paths = _build_expected_s3_paths(metadata)
                verify_handler = VerifyParquetFiles(
                    schema_name=self.schema_name,
                    provider_uuid=metadata["uuid"],
                    provider_type=metadata["type"],
                    simulate=True,
                    bill_date=bill_date,
                    cleaned_column_mapping=self.required_columns,
                )
                s3_prefixes = verify_handler._generate_s3_path_prefixes(bill_date)
                self.assertEqual(len(s3_prefixes), len(expected_s3_paths))
                for expected_path in expected_s3_paths:
                    self.assertIn(expected_path, s3_prefixes)

    @patch("masu.api.upgrade_trino.util.verify_parquet_files.StateTracker._clean_local_files")
    @patch("masu.api.upgrade_trino.util.verify_parquet_files.get_s3_resource")
    def test_retrieve_verify_reload_s3_parquet_failure(self, mock_s3_resource, _):
        """Test fixes for reindexes on all required columns."""
        # build a parquet file where reindex is used for all required columns
        file_data = {
            "float": [datetime(2023, 1, 1), datetime(2023, 1, 1), datetime(2023, 1, 1)],
            "string": ["A", "B", "C"],
            "datetime": [datetime(2023, 1, 1), datetime(2023, 1, 2), datetime(2023, 1, 3)],
        }

        bill_date = str(DateHelper().this_month_start)
        temp_file = os.path.join(self.temp_dir, f"fail{self.suffix}")
        pd.DataFrame(file_data).to_parquet(temp_file, **self.panda_kwargs)
        mock_bucket = mock_s3_resource.return_value.Bucket.return_value
        verify_handler = VerifyParquetFiles(
            schema_name=self.schema_name,
            provider_uuid=self.aws_provider_uuid,
            provider_type=self.aws_provider.type,
            simulate=True,
            bill_date=bill_date,
            cleaned_column_mapping=self.required_columns,
        )
        prefixes = verify_handler._generate_s3_path_prefixes(DateHelper().this_month_start)
        filter_side_effect = [[DummyS3Object(key=temp_file)]]
        for _ in range(len(prefixes) - 1):
            filter_side_effect.append([])
        mock_bucket.objects.filter.side_effect = filter_side_effect
        mock_bucket.download_file.return_value = temp_file
        VerifyParquetFiles.local_path = Path(self.temp_dir)
        verify_handler.retrieve_verify_reload_s3_parquet()
        mock_bucket.upload_fileobj.assert_not_called()
        os.remove(temp_file)

    def test_local_path(self):
        """Test local path."""
        verify_handler = self.create_default_verify_handler()
        self.assertTrue(verify_handler.local_path)
