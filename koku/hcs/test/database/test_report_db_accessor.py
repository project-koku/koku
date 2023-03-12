#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test HCSReportDBAccessor."""
from datetime import timedelta
from unittest.mock import MagicMock
from unittest.mock import patch

from api.models import Provider
from api.utils import DateHelper
from hcs.database.report_db_accessor import HCSReportDBAccessor
from hcs.test import HCSTestCase


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
        self.assertNotEqual(dba.jinja_sql, None)
        self.assertNotEqual(dba.date_accessor, None)

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
            self.assertIn("acquiring marketplace data...", _logs.output[0])
            self.assertIn(f"schema: {self.schema}, provider: {self.provider}, date: {self.today}", _logs.output[1])
            self.assertIn("no data found for date", _logs.output[2])

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
            self.assertIn("acquiring marketplace data...", _logs.output[0])
            self.assertIn(f"schema: {self.schema}, provider: {self.provider}, date: {self.today}", _logs.output[1])
            self.assertIn("data found for date", _logs.output[2])
