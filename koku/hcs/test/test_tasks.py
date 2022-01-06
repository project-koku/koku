#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the HCS task."""
import logging
from datetime import timedelta

from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_data
from hcs.test import HCSTestCase

LOG = logging.getLogger(__name__)


class TestHCSTasks(HCSTestCase):
    """Test cases for HCS Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def test_get_report_dates(self):
        """Test with start and end dates provided"""
        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            end_date = self.today
            collect_hcs_report_data(start_date, end_date)

            self.assertIn(f"OUTPUT FROM HCS TASK, Start-date: {start_date}, End-date: {end_date}", _logs.output[0])

    def test_get_report_no_start_date(self):
        """Test to with no start or end dates provided"""
        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.today
            collect_hcs_report_data()

            self.assertIn(f"OUTPUT FROM HCS TASK, Start-date: {start_date}", _logs.output[0])

    def test_get_report_no_end_date(self):
        """TTest to with no start end provided"""
        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(start_date)

            self.assertIn(f"OUTPUT FROM HCS TASK, Start-date: {start_date}", _logs.output[0])
