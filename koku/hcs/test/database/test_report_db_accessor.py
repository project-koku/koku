#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCSReportDBAccessor."""
import time
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from trino.exceptions import TrinoExternalError

from api.models import Provider
from api.utils import DateHelper
from hcs.database.report_db_accessor import HCSReportDBAccessor
from hcs.test import HCSTestCase
from koku.trino_database import retry
from koku.trino_database import TrinoNoSuchKeyError
from masu.database.report_db_accessor_base import ReportDBAccessorBase


def mock_sql_query(self, schema, sql, bind_params=None):
    return "12345"


class TestHCSReportDBAccessor(HCSTestCase):
    """Test cases for HCS DB Accessor."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_init(self):
        """Test the initializer."""
        dba = HCSReportDBAccessor("org1234567")
        self.assertEqual(dba.schema, "org1234567")

    def test_no_sql_file(self):
        """Test with start and end dates provided"""
        with self.assertLogs("hcs.database", "ERROR") as _logs:
            hcs_accessor = HCSReportDBAccessor(self.schema)
            hcs_accessor.get_hcs_daily_summary(
                self.today,
                self.provider,
                self.provider_uuid,
                "bogus_sql_file",
                "1234-1234-1234",
            )
            self.assertIn("unable to locate SQL file", _logs.output[0])
            self.assertRaises(FileNotFoundError)

    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query_with_description")
    def test_no_data_hcs_customer(self, mock_dba_query, mock_dba):
        """Test no data found for specified date"""
        mock_dba_query.return_value = (MagicMock(), MagicMock())

        with self.assertLogs("hcs.database", "INFO") as _logs:
            hcs_accessor = HCSReportDBAccessor(self.schema)
            hcs_accessor.get_hcs_daily_summary(
                self.today,
                self.provider,
                self.provider_uuid,
                "sql/reporting_aws_hcs_daily_summary.sql",
                "1234-1234-1234",
            )
            self.assertIn("acquiring marketplace data", _logs.output[0])
            self.assertIn("no data found", _logs.output[1])

    @patch("hcs.csv_file_handler.CSVFileHandler")
    @patch("hcs.csv_file_handler.CSVFileHandler.write_csv_to_s3")
    @patch("masu.database.report_db_accessor_base.ReportDBAccessorBase._execute_trino_raw_sql_query_with_description")
    def test_data_hcs_customer(self, mock_dba_query, mock_fh_writer, mock_fh):
        """Test data found for specified date"""
        mock_dba_query.return_value = (MagicMock(), MagicMock())

        with self.assertLogs("hcs.database", "INFO") as _logs:
            hcs_accessor = HCSReportDBAccessor(self.schema)
            hcs_accessor.get_hcs_daily_summary(
                self.today,
                self.provider,
                self.provider_uuid,
                "sql/reporting_aws_hcs_daily_summary.sql",
                "1234-1234-1234",
            )
            self.assertIn("acquiring marketplace data", _logs.output[0])
            self.assertIn("data found", _logs.output[1])

    @patch("koku.trino_database.connect")
    def test_no_retry_on_trino_external_error(self, mock_connect):
        """Test that we don't retry on TrinoError that aren't NoSuchKey related."""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = TrinoExternalError({"message": "TrinoError"})
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        accessor = ReportDBAccessorBase(schema="test_schema")

        with (
            self.assertRaises(TrinoExternalError),
            # No log messages indicates no retries
            self.assertLogs("koku.trino_database", "ERROR") as error_logs,
        ):
            accessor._execute_trino_raw_sql_query_with_description(
                "SELECT * FROM table",
                sql_params={},
                context={},
                log_ref="Test Log Ref",
                conn_params={},
            )

        self.assertFalse(error_logs.output)

    @patch("koku.trino_database.connect")
    def test_trino_no_such_key_exception_retries(self, mock_connect):
        """Test if retries are attempted when TrinoNoSuchKeyError is raised."""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = TrinoExternalError({"message": "NoSuchKey"})
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        accessor = ReportDBAccessorBase(schema="test_schema")
        sql = "SELECT * FROM table"
        sql_params = {}
        context = {}
        log_ref = "Test Log Ref"
        conn_params = {}

        with (
            self.assertRaises(TrinoNoSuchKeyError),
            self.assertLogs("koku.trino_database", "ERROR") as error_logs,
            patch("time.sleep", return_value=None),
        ):
            accessor._execute_trino_raw_sql_query_with_description(
                sql,
                sql_params=sql_params,
                context=context,
                log_ref=log_ref,
                conn_params=conn_params,
            )

        self.assertIn("failed execution", error_logs.output[0].lower())

    @patch("time.sleep", side_effect=None)
    def test_retry_backoff_and_jitter(self, mock_sleep):
        """Test delay for retries."""

        call_attempts = []

        @retry(retry_on=(Exception,), max_wait=30, retries=3)
        def function_that_fails():
            call_attempts.append(time.time())
            raise TrinoNoSuchKeyError("NoSuchKey error occurred")

        with self.assertRaises(TrinoNoSuchKeyError):
            function_that_fails()

        # Check the number of delay values
        delay_values = [call.args[0] for call in mock_sleep.call_args_list]
        print(f"Delay values: {delay_values}")
        self.assertEqual(len(delay_values), 2, "Should retry exactly 3 times")

        # Check that the delay increases with each retry
        for i in range(1, len(delay_values)):
            self.assertTrue(delay_values[i] >= delay_values[i - 1], "Delay should increase with each retry")

        # Check that the delays include jitter
        base_delays = [min(2**i, 30) for i in range(3)]
        for base, actual in zip(base_delays, delay_values):
            self.assertTrue(base <= actual < base + 1, "Jitter should be between 0 and 1")

    @patch("time.sleep", side_effect=None)
    @patch("koku.trino_database.LOG")
    def test_retry_logic_and_logging(self, mock_log, mock_sleep):
        """Test retry logic and logging for retries and errors."""

        @retry(retry_on=(Exception,), retries=3, max_wait=30)
        def function_that_fails():
            raise TrinoNoSuchKeyError("NoSuchKey error occurred")

        with self.assertRaises(TrinoNoSuchKeyError):
            function_that_fails()

        self.assertEqual(mock_sleep.call_count, 2)

        delay_values = [call.args[0] for call in mock_sleep.call_args_list]
        for i in range(1, len(delay_values)):
            self.assertTrue(delay_values[i] > delay_values[i - 1], "Delay should increase with each retry")

        self.assertTrue(any("Retrying..." in str(call) for call in mock_log.warning.call_args_list))
        self.assertTrue(any("Failed execution after" in str(call) for call in mock_log.error.call_args_list))
