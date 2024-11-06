#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test cases for VataValidator"""
from unittest.mock import patch

from trino.exceptions import TrinoExternalError

from api.provider.models import Provider
from api.utils import DateHelper
from masu.processor._tasks.data_validation import DataValidator
from masu.processor._tasks.data_validation import PG_FILTER_MAP
from masu.processor._tasks.data_validation import PG_TABLE_MAP
from masu.processor._tasks.data_validation import TRINO_FILTER_MAP
from masu.processor._tasks.data_validation import TRINO_TABLE_MAP
from masu.test import MasuTestCase


class TestDataValidator(MasuTestCase):
    """Test Cases for the data validator."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.start_date = DateHelper().now_utc
        cls.end_date = DateHelper().now_utc
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_init(self):
        """Test the initializer."""
        cloud_type = "GCP"
        context = "test"
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, cloud_type, context=context
        )
        self.assertEqual(validator.schema, self.schema)
        self.assertEqual(validator.ocp_on_cloud_type, cloud_type)
        self.assertEqual(validator.provider_uuid, self.provider_uuid)
        self.assertEqual(validator.context, context)

    def test_get_provider_table_filters(self):
        """Testing the lookup for a particular provider."""
        provider_type = "GCP"
        context = "test"
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, None, context=context
        )

        # Test Postgres lookup
        table, query_filters = validator.get_table_filters_for_provider(provider_type)
        self.assertEqual(table, PG_TABLE_MAP.get(provider_type))
        self.assertEqual(query_filters, PG_FILTER_MAP.get(provider_type))

        # Test Trino lookup
        table, query_filters = validator.get_table_filters_for_provider(provider_type, trino=True)
        self.assertEqual(table, TRINO_TABLE_MAP.get(provider_type))
        self.assertEqual(query_filters, TRINO_FILTER_MAP.get(provider_type))

        # Test Trino OCP ON CLOUD lookup
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, "GCP", context=context
        )
        table, query_filters = validator.get_table_filters_for_provider(provider_type, trino=True)
        self.assertEqual(table, TRINO_TABLE_MAP.get("OCPGCP"))
        self.assertEqual(query_filters, TRINO_FILTER_MAP.get("OCPGCP"))

    def test_compare_data(self):
        """Test comparing input data."""
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, None, context="test"
        )
        # Test no trino data
        incomplete_days, valid_cost = validator.compare_data({}, {})
        self.assertTrue(valid_cost)
        self.assertEqual(incomplete_days, {})

        # Test valid data
        data = {"date": 30}
        incomplete_days, valid_cost = validator.compare_data(data, data)
        self.assertTrue(valid_cost)
        self.assertEqual(incomplete_days, {})

        # Test inaccurate data
        day = "date2"
        trino_data = {"date1": 30, day: 20}
        pg_data = {"date1": 30, day: 10}
        expected_incomplete_days = {
            day: {
                "pg_value": pg_data[day],
                "trino_value": trino_data[day],
                "delta": trino_data[day] - pg_data[day],
            }
        }
        incomplete_days, valid_cost = validator.compare_data(pg_data, trino_data)
        self.assertFalse(valid_cost)
        self.assertEqual(incomplete_days, expected_incomplete_days)

        # Test missing data
        day = "date2"
        trino_data = {"date1": 30, day: 20}
        pg_data = {"date1": 30}
        expected_incomplete_days = {day: "missing daily data"}
        incomplete_days, valid_cost = validator.compare_data(pg_data, trino_data)
        self.assertFalse(valid_cost)
        self.assertEqual(incomplete_days, expected_incomplete_days)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._prepare_and_execute_raw_sql_query")
    def test_query_postgres(self, mock_pg_query):
        """Test making postgres queries."""
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, None, context="test"
        )
        validator.execute_relevant_query("AWS")
        mock_pg_query.assert_called()

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_query_trino(self, mock_trino_query):
        """Test making trino queries."""
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, None, context="test"
        )
        validator.execute_relevant_query("AWS", trino=True)
        mock_trino_query.assert_called()

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_query_result(self, mock_trino_query):
        """Test making trino queries."""
        date = DateHelper().today
        expected_result = {date.date(): 30.0}
        mock_trino_query.return_value = [[30, date]]
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.provider_uuid, None, context="test"
        )
        result = validator.execute_relevant_query("AWS", trino=True)
        self.assertEqual(result, expected_result)

    @patch("masu.processor._tasks.data_validation.DataValidator.execute_relevant_query")
    def test_check_data_integrity(self, mock_query):
        """Test for valid data."""
        date = DateHelper().today
        mock_query.return_value = {date: 30}
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.aws_provider_uuid, None, context={"test": "testing"}
        )
        with self.assertLogs("masu.processor._tasks.data_validation", level="INFO") as logger:
            validator.check_data_integrity()
            expected = "all data complete for provider"
            found = any(expected in log for log in logger.output)
            self.assertTrue(found)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._prepare_and_execute_raw_sql_query")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_check_data_integrity_pg_error(self, mock_trino_query, mock_pg_query):
        """Test for pg query error."""
        mock_pg_query.side_effect = Exception("Error")
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.aws_provider_uuid, None, context={"test": "testing"}
        )
        with self.assertLogs("masu.processor._tasks.data_validation", level="WARNING") as logger:
            validator.check_data_integrity()
            expected = "data validation postgres query failed"
            found = any(expected in log for log in logger.output)
            self.assertTrue(found)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._prepare_and_execute_raw_sql_query")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_check_data_integrity_trino_error(self, mock_trino_query, mock_pg_query):
        """Test for trino query error."""
        mock_trino_query.side_effect = Exception("Error")
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.aws_provider_uuid, None, context={"test": "testing"}
        )
        with self.assertLogs("masu.processor._tasks.data_validation", level="WARNING") as logger:
            validator.check_data_integrity()
            expected = "data validation trino query failed"
            found = any(expected in log for log in logger.output)
            self.assertTrue(found)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._prepare_and_execute_raw_sql_query")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_partition_dropped_during_verification(self, mock_trino_query, mock_pg_query):
        """Test that 'Partition no longer exists' error is handled correctly."""
        error_mock = {"errorType": "EXTERNAL", "message": "Partition no longer exists"}
        mock_trino_query.side_effect = TrinoExternalError(error_mock, query_id="fake_id")
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.aws_provider_uuid, None, context={"test": "testing"}
        )
        with self.assertLogs("masu.processor._tasks.data_validation", level="INFO") as logger:
            validator.check_data_integrity()
            self.assertTrue(any("Partition dropped during verification" in log for log in logger.output))

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._prepare_and_execute_raw_sql_query")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query")
    def test_partition_dropped_during_verification_unknown_error(self, mock_trino_query, mock_pg_query):
        """Test that error is handled correctly."""
        err_msg = "Unknown"
        error_mock = {"errorType": "EXTERNAL", "message": err_msg}
        mock_trino_query.side_effect = TrinoExternalError(error_mock, query_id="fake_query")
        validator = DataValidator(
            self.schema, self.start_date, self.end_date, self.aws_provider_uuid, None, context={"test": "testing"}
        )
        with self.assertLogs("masu.processor._tasks.data_validation", level="INFO") as logger:
            validator.check_data_integrity()
            self.assertTrue(any(err_msg in log for log in logger.output))
