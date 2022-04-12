#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the HCS task."""
import logging
from datetime import timedelta
from unittest.mock import patch

from api.models import Provider
from api.utils import DateHelper
from hcs.test import HCSTestCase

LOG = logging.getLogger(__name__)


def enable_hcs_processing_mock(schema=True):
    tf = schema

    return tf


@patch("hcs.tasks.enable_hcs_processing", enable_hcs_processing_mock)
@patch("hcs.daily_report.ReportHCS")
class TestHCSTasks(HCSTestCase):
    """Test cases for HCS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)
        cls.provider = Provider.PROVIDER_AWS
        cls.provider_uuid = "cabfdddb-4ed5-421e-a041-311b75daf235"

    def test_get_report_dates(self, mock_report):
        """Test with start and end dates provided"""
        from hcs.tasks import collect_hcs_report_data

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            end_date = self.today
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid, start_date, end_date)

            self.assertIn("Running HCS data collection", _logs.output[0])

    def test_get_report_no_start_date(self, mock_report):
        """Test no start or end dates provided"""
        from hcs.tasks import collect_hcs_report_data

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid)

            self.assertIn("Running HCS data collection", _logs.output[0])

    def test_get_report_no_end_date(self, mock_report):
        """Test no start end provided"""
        from hcs.tasks import collect_hcs_report_data

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, self.provider, self.provider_uuid, start_date)

            self.assertIn("Running HCS data collection", _logs.output[0])

    def test_get_report_invalid_provider(self, mock_report):
        """Test invalid provider"""
        from hcs.tasks import collect_hcs_report_data

        enable_hcs_processing_mock.tf = False

        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(self.schema, "bogus", self.provider_uuid, start_date)

            self.assertIn("Customer not registered with HCS", _logs.output[0])

    def test_schema_no_acct_prefix(self, mock_report):
        """Test no start end provided"""
        from hcs.tasks import collect_hcs_report_data

        collect_hcs_report_data("10001", self.provider, self.provider_uuid, self.yesterday)

        self.assertEqual("acct10001", self.schema)
