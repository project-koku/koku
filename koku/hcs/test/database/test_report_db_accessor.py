#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCSReportDBAccessor."""
from datetime import timedelta
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import patch

from trino.exceptions import TrinoExternalError

from api.models import Provider
from api.utils import DateHelper
from hcs.database.report_db_accessor import HCSReportDBAccessor
from hcs.test import HCSTestCase
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

    def test_handle_trino_external_error_with_no_such_key(self):
        """Test handle_trino_external_error with NoSuchKey error."""
        accessor = ReportDBAccessorBase(schema="test_schema")

        with patch.object(accessor, "_execute_trino_raw_sql_query_with_description") as mock_retry, patch(
            "masu.database.report_db_accessor_base.LOG"
        ) as mock_log:
            accessor._handle_trino_external_error(
                "NoSuchKey", "SELECT * FROM table", {}, {}, "Test Log Ref", 1, 3, {}, {}
            )

            mock_retry.assert_called_once()
            mock_log.warning.assert_called()
            mock_log.error.assert_not_called()

    def test_handle_trino_external_error_without_no_such_key(self):
        """Test handle_trino_external_error without NoSuchKey error."""
        accessor = ReportDBAccessorBase(schema="test_schema")
        error_instance = TrinoExternalError({"error": "Trino Error"})

        with (
            patch.object(accessor, "_execute_trino_raw_sql_query_with_description") as mock_retry,
            patch("masu.database.report_db_accessor_base.LOG") as mock_log
        ):
            self.assertRaises(TrinoExternalError):
            accessor._handle_trino_external_error(
                error_instance, "SELECT * FROM table", {}, {}, "Test Log Ref", 1, 3, {}, {}
            )

        mock_retry.assert_not_called()
        mock_log.error.assert_called()

    @mock.patch("koku.trino_database.connect")
    def test_handle_trino_external_error_invocation(self, mock_connect):
        """Test handle_trino_external_error invocation."""
        mock_cursor = mock.MagicMock()
        mock_cursor.execute.side_effect = TrinoExternalError({"error": "Trino Error"})
        mock_conn = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        accessor = ReportDBAccessorBase(schema="test_schema")
        sql = "SELECT * FROM test_table"
        sql_params = {"param1": "value1"}
        context = {}
        log_ref = "Test Query"
        attempts_left = 1
        trino_external_error_retries = 1
        conn_params = {}

        with self.assertRaises(TrinoExternalError):
            accessor._execute_trino_raw_sql_query_with_description(
                sql,
                sql_params=sql_params,
                context=context,
                log_ref=log_ref,
                attempts_left=attempts_left,
                trino_external_error_retries=trino_external_error_retries,
                conn_params=conn_params,
            )
