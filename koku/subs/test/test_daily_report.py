#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for SUBS daily report."""
from datetime import timedelta
from unittest.mock import patch

from subs.daily_report import ReportSUBS
from subs.test import SUBSTestCase


class TestReportSUBS(SUBSTestCase):
    """Test cases for the ReportSUBS class."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()

    def setUp(self):
        """Set up each test."""
        super().setUp()

        self.tracing_id = "6e8db12f-d8e3-4e28-91c8-25fe9b4c6fd8"
        self.start_date = self.dh.today - timedelta(days=2)
        self.end_date = self.dh.today
        self.reportSUBS = ReportSUBS(self.schema_name, self.aws_provider_type, self.aws_provider_uuid, self.tracing_id)

    def test_init(self):
        """Test the initialization of the ReportSUBS class."""

        self.assertEqual(self.reportSUBS._schema_name, self.schema_name)
        self.assertEqual(self.reportSUBS._provider, self.aws_provider_type.removesuffix("-local"))
        self.assertEqual(self.reportSUBS._provider_uuid, self.aws_provider_uuid)
        self.assertEqual(self.reportSUBS._tracing_id, self.tracing_id)

    @patch("logging.Logger.info")
    def test_generate_report(self, mock_log_info):
        """Test the generate_report function of the ReportSUBS class."""
        self.reportSUBS.generate_report(self.start_date, self.end_date)
        mock_log_info.assert_called()
