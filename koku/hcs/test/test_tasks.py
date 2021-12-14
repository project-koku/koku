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
    """Test cases for Processor Celery tasks."""

    @classmethod
    def setUpClass(cls):
        """Set up the class."""
        super().setUpClass()
        cls.today = DateHelper().today
        cls.yesterday = cls.today - timedelta(days=1)

    def test_get_report_dates(self):
        """Test raising download warning is handled."""
        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            end_date = self.today
            collect_hcs_report_data(start_date, end_date)

            self.assertIn(f"OUTPUT FROM HCS TASK, Start-date: {start_date}, End-date: {end_date}", _logs.output[0])

    def test_get_report_no_end_date(self):
        """Test raising download warning is handled."""
        with self.assertLogs("hcs.tasks", "INFO") as _logs:
            start_date = self.yesterday
            collect_hcs_report_data(start_date)

            self.assertIn(f"OUTPUT FROM HCS TASK, Start-date: {start_date}", _logs.output[0])
